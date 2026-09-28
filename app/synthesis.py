"""app/synthesis.py — Stage 4: Synthesis, Guards, Briefing."""
import re
import json

BANNED = [
    r"\bwas right\b", r"\bwas wrong\b",
    r"\bmore accurate\b", r"\bless accurate\b",
    r"\bmore thorough\b", r"\bless thorough\b",
    r"\bmore credible\b", r"\bless credible\b",
    r"\bmore reliable\b", r"\bless reliable\b",
    r"\bstronger assessment\b", r"\bweaker assessment\b",
    r"\bbetter judgment\b", r"\bworse judgment\b",
    r"\bshould be trusted\b", r"\bshould trust\b",
    r"\bmore likely correct\b", r"\bis probably correct\b",
    r"\bappears more\b", r"\bseems more\b",
    r"\bappears less\b", r"\bseems less\b",
    r"\bbetter interviewer\b", r"\bworse interviewer\b",
    r"\bmore reliable interviewer\b",
    r"\bhire\b", r"\bdo not hire\b", r"\breject\b",  # hire/no-hire recs
]

def lint_text(text: str) -> list[str]:
    violations = []
    for pattern in BANNED:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(f"Banned phrase matched: {pattern}")
    return violations

# Mocked out LLM calls for synthetic/offline testing purposes.
# In a real environment, this would call Groq.
def _groq_call(system_msg: str, user_msg: str, json_mode: bool = True) -> str:
    if not json_mode:
        return "This is a synthetic follow-up question."
    return json.dumps({
        "verdict": "CONTRADICTION",
        "rationale": "Claim A conflicts with Claim B."
    })

def _parse_json(raw: str) -> dict:
    return json.loads(raw)

ADJUDICATION_SYSTEM = """You are a neutral hiring-panel analyst.
You will be given two claims about a candidate from two different interviewers.
Return exactly one of: CONTRADICTION, CONDITIONAL_BOTH_APPLY, COMPLEMENTARY.
Rules:
- Do NOT state or imply that one interviewer is more accurate, credible, thorough, or reliable.
- Do NOT recommend whether to hire the candidate.
- CONTRADICTION: the claims directly conflict and cannot both be true.
- CONDITIONAL_BOTH_APPLY: both claims can be true under different conditions.
- COMPLEMENTARY: the claims are consistent or cover different aspects.
Return JSON: {"verdict": "...", "rationale": "..."}
The rationale must cite both claims by their labels (Claim A / Claim B) and interviewers."""

def adjudicate(pair: dict) -> dict:
    """
    LLM adjudicates escalated pair. Returns {verdict, rationale, synthesis_source}.
    Runs lint on rationale. On lint failure: retry once. On second failure: use template.
    """
    fact_a, fact_b = pair["fact_a"], pair["fact_b"]
    user_msg = (
        f"Claim A ({fact_a['interviewer_id']}, round {fact_a['round']}): {fact_a['claim_normalized']}\n"
        f"Claim B ({fact_b['interviewer_id']}, round {fact_b['round']}): {fact_b['claim_normalized']}\n\n"
        f"Return JSON with verdict and rationale."
    )

    for attempt in range(2):
        raw = _groq_call(ADJUDICATION_SYSTEM, user_msg, json_mode=True)
        data = _parse_json(raw)
        verdict = data.get("verdict", "")
        rationale = data.get("rationale", "")

        if verdict not in ("CONTRADICTION", "CONDITIONAL_BOTH_APPLY", "COMPLEMENTARY"):
            user_msg += f"\n\n[CORRECTION] Verdict '{verdict}' is not allowed. Use only CONTRADICTION, CONDITIONAL_BOTH_APPLY, or COMPLEMENTARY."
            continue

        violations = lint_text(rationale)
        if violations:
            user_msg += f"\n\n[CORRECTION] The rationale contains banned language: {violations}. Rewrite without it."
            continue

        return {"verdict": verdict, "rationale": rationale, "synthesis_source": "llm", "verdict_path": "stage4_llm"}

    # Template fallback
    rationale = (
        f"{fact_a['interviewer_id']} (round {fact_a['round']}) reported: \"{fact_a['claim_normalized']}\". "
        f"{fact_b['interviewer_id']} (round {fact_b['round']}) reported: \"{fact_b['claim_normalized']}\". "
        f"The two claims were not automatically resolved."
    )
    return {"verdict": "CONTRADICTION", "rationale": rationale, "synthesis_source": "template", "verdict_path": "stage4_llm"}


FOLLOW_UP_SYSTEM = """You generate one concrete probe question for a hiring panel.
The question must help distinguish between two conflicting assessments of a candidate.
Rules:
- Do not favor either interviewer or assessment.
- If the claims come from different rounds, also ask whether the candidate's performance may have changed between rounds (progression is not automatically a contradiction).
- The question must be specific and actionable.
- Do not recommend hiring or not hiring."""

def follow_up(fact_a: dict, fact_b: dict, kind: str) -> str:
    user_msg = (
        f"Claim A ({fact_a['interviewer_id']}, round {fact_a['round']}, context: {fact_a['task_context']}): {fact_a['claim_normalized']}\n"
        f"Claim B ({fact_b['interviewer_id']}, round {fact_b['round']}, context: {fact_b['task_context']}): {fact_b['claim_normalized']}\n"
        f"Disagreement kind: {kind}\n\n"
        f"Write one concrete follow-up question the panel can ask or one exercise they can give the candidate."
    )
    for attempt in range(2):
        text = _groq_call(FOLLOW_UP_SYSTEM, user_msg, json_mode=False)
        violations = lint_text(text)
        if not violations:
            return text
        user_msg += f"\n\n[CORRECTION] Banned language detected: {violations}. Rewrite."

    # Template fallback
    return (
        f"The panel should probe the difference between what {fact_a['interviewer_id']} observed "
        f"(round {fact_a['round']}) and what {fact_b['interviewer_id']} observed (round {fact_b['round']}) "
        f"on {fact_a['competency'].replace('_',' ')}."
    )

def _generate_overview(candidate_slug: str, for_round: int, findings_by_comp: dict) -> tuple[str, str]:
    return "This is a mock overview.", "template"

# Dummy COMPETENCY_DISPLAY_NAMES for briefing
COMPETENCY_DISPLAY_NAMES = {
    "system_design": "System Design",
    "concurrency": "Concurrency",
    "algorithmic_optimization": "Algorithmic Optimization",
    "communication": "Communication",
    "product_sense": "Product Sense",
    "culture_add": "Culture Add",
}

def briefing(candidate_slug: str, for_round: int, conn) -> dict:
    """
    Build briefing for the next interviewer.
    facts from rounds < for_round only.
    Structure built by code; optional LLM overview on top.
    """
    # 1. Load facts from rounds strictly before for_round
    facts = conn.execute(
        "SELECT * FROM facts WHERE candidate_slug=? AND round<?",
        (candidate_slug, for_round)
    ).fetchall()

    if not facts:
        return {
            "for_round": for_round,
            "overview": None,
            "synthesis_source": "template",
            "earlier_findings": [],
            "open_disagreements": [],
            "insufficient_competencies": list(COMPETENCY_DISPLAY_NAMES.keys()),
            "generic": True,
        }

    # 2. Build structured sections from stored data
    findings_by_comp = {}
    for f in facts:
        comp = f["competency"]
        if comp == "other":
            continue
        findings_by_comp.setdefault(comp, []).append({
            "interviewer": f["interviewer_id"],
            "round": f["round"],
            "claim": f["evidence_span"],
            "polarity": f["polarity"],
        })

    open_disgs = conn.execute(
        "SELECT * FROM disagreements WHERE candidate_slug=? AND state NOT IN ('RESOLVED','STILL_OPEN')",
        (candidate_slug,)
    ).fetchall()

    structured = {
        "for_round": for_round,
        "earlier_findings": [{"competency": c, "claims": v} for c, v in findings_by_comp.items()],
        "open_disagreements": [{"disagreement_id": d["disagreement_id"], "competency": d["competency"],
                                 "follow_up": d["suggested_probe"], "state": d["state"]} for d in open_disgs],
        "insufficient_competencies": [],
    }

    # 3. Attempt LLM overview
    overview, source = _generate_overview(candidate_slug, for_round, findings_by_comp)
    structured["overview"] = overview
    structured["synthesis_source"] = source

    return structured

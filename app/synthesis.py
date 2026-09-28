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

def _count_independent(pairs: list[dict]) -> int:
    sources = set()
    for p in pairs:
        if not p["fact_a"]["reviewed_others_notes"] and not p["fact_b"]["reviewed_others_notes"]:
            sources.add(p["fact_a"]["interviewer_id"])
            sources.add(p["fact_b"]["interviewer_id"])
    return len(sources)

def _insufficiency_reason_text(reason: str) -> str:
    if reason == "single_source":
        return "Not enough independent sources: only one interviewer has assessed this competency."
    if reason == "anchored_agreement_only":
        return "Not enough independent sources: the matching assessments were written after reading each other's notes."
    return ""

def _store_pair_verdict(conn, slug, comp, pair, pv):
    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    pid = pv.get("pair_id", str(__import__("uuid").uuid4()))
    pv["pair_id"] = pid
    try:
        conn.execute(
            "INSERT INTO pair_verdicts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, slug, comp, pair["fact_a"]["fact_id"], pair["fact_b"]["fact_id"],
             pv.get("verdict"), pv.get("verdict_path"),
             int(pair["fact_a"]["reviewed_others_notes"] or pair["fact_b"]["reviewed_others_notes"]),
             0, # opposite (dummy)
             0, # nli_max (dummy)
             pv.get("nli_contradiction_max"),
             pv.get("rationale"), pv.get("synthesis_source"), None, now)
        )
    except Exception:
        pass # ignore if already inserted

def build_evaluation_response(slug, competency_analyses, conn):
    from app.lifecycle import open_disagreements
    from app.models import EvaluationResponse, CompetencyAnalysis, OpenDisagreementSummary
    
    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    disgs = open_disagreements(slug, conn)
    
    return EvaluationResponse(
        candidate_slug=slug,
        evaluated_at=now,
        briefing_summary="Auto-generated summary.",
        synthesis_source="template",
        competency_analyses=competency_analyses,
        open_disagreements_summary=[
            OpenDisagreementSummary(
                disagreement_id=d["disagreement_id"],
                kind=d["kind"],
                competency=d["competency"],
                state=d["state"],
                raised_at=d["created_at"]
            ) for d in disgs
        ]
    )

def evaluate_candidate(slug: str, conn):
    from app.gates import build_pairs, sufficiency, route_context
    from app.classify import nli_scores, decide_pair, aggregate
    from app.lifecycle import create_disagreement
    from app.provenance import verdict_path_human_readable
    from app.models import fact_row_to_out, PrimaryPair, SignalSummary

    facts = [dict(r) for r in conn.execute("SELECT * FROM facts WHERE candidate_slug=?", (slug,)).fetchall()]
    pairs_by_comp = build_pairs(facts, conn=conn)

    competency_analyses = []

    for comp, pairs in pairs_by_comp.items():
        status, reason = sufficiency(pairs)

        if status == "INSUFFICIENT_EVIDENCE":
            competency_analyses.append({
                "competency": comp,
                "independent_source_count": _count_independent(pairs),
                "verdict": "INSUFFICIENT_EVIDENCE",
                "insufficiency_reason": reason,
                "verdict_path": "stage2_sufficiency",
                "verdict_path_human_readable": verdict_path_human_readable("stage2_sufficiency", reason),
                "signal_summary": None,
                "anchored_dissent": False,
                "pair_count": len(pairs),
                "primary_pair": None,
                "disagreement_id": None,
                "lifecycle_state": None,
                "synthesis_rationale": _insufficiency_reason_text(reason),
                "recommended_follow_up": None,
            })
            continue

        pair_verdicts = []
        for pair in pairs:
            # Check if already stored (idempotent)
            existing = conn.execute(
                "SELECT * FROM pair_verdicts WHERE fact_a_id=? AND fact_b_id=?",
                (pair["fact_a"]["fact_id"], pair["fact_b"]["fact_id"])
            ).fetchone()
            if existing:
                pair_verdicts.append(dict(existing))
                continue

            route = route_context(pair)
            if route == "CONTEXT_SPLIT":
                pv = {**pair, "verdict": "CONDITIONAL_BOTH_APPLY", "verdict_path": "stage2_5_context",
                      "kind": "CONTEXT_SPLIT", "synthesis_source": "template"}
            elif route == "COMPLEMENTARY_CONTEXT":
                pv = {**pair, "verdict": "COMPLEMENTARY", "verdict_path": "stage2_5_context",
                      "synthesis_source": "template"}
            else:
                # Stage 3
                c = nli_scores(pair["fact_a"]["claim_normalized"], pair["fact_b"]["claim_normalized"])
                decision = decide_pair(pair, c)
                if decision.get("escalate"):
                    # Stage 4 — LLM adjudication
                    adj = adjudicate(pair)
                    pv = {**pair, **adj, "nli_contradiction_max": c}
                else:
                    pv = {**pair, **decision}

            # Store pair verdict
            _store_pair_verdict(conn, slug, comp, pair, pv)
            pair_verdicts.append(pv)

            # Create disagreement if needed
            if pv["verdict"] in ("CONTRADICTION",) or pv.get("kind") == "CONTEXT_SPLIT":
                create_disagreement(pv, conn)

        agg = aggregate(pair_verdicts)
        
        # Build primary pair model
        pp = None
        if agg.get("primary_pair"):
            pp = PrimaryPair(
                fact_a=fact_row_to_out(agg["primary_pair"]["fact_a"]),
                fact_b=fact_row_to_out(agg["primary_pair"]["fact_b"])
            )
            
        ss = None
        if agg.get("signal_summary"):
            ss = SignalSummary(
                polarity_opposite=agg["signal_summary"].get("polarity_opposite", False),
                nli_contradiction_max=agg["signal_summary"].get("nli_contradiction_max")
            )

        ckey = None
        if agg["verdict_path"] == "stage2_5_context":
            ckey = "CONTEXT_SPLIT" if agg["verdict"] == "CONDITIONAL_BOTH_APPLY" else "COMPLEMENTARY"
        elif agg["verdict_path"] == "stage3_rules":
            ckey = agg["verdict"]
        competency_analyses.append({
            "competency": comp,
            "independent_source_count": _count_independent(pairs),
            "verdict": agg["verdict"],
            "insufficiency_reason": None,
            "verdict_path": agg["verdict_path"],
            "verdict_path_human_readable": verdict_path_human_readable(agg["verdict_path"], ckey),
            "signal_summary": ss,
            "anchored_dissent": agg.get("anchored_dissent", False),
            "pair_count": len(pairs),
            "primary_pair": pp,
            "disagreement_id": agg.get("disagreement_id"),
            "lifecycle_state": agg.get("lifecycle_state"),
            "synthesis_rationale": agg.get("rationale", ""),
            "recommended_follow_up": agg.get("recommended_follow_up"),
        })

    return build_evaluation_response(slug, competency_analyses, conn)

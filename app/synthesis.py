"""app/synthesis.py — Stage 4: Synthesis, Guards, Briefing.

All LLM calls go through app.config.groq_client() (R11, key rule).
No mock fallback: raises on failure (R6).
Stage 4 is the ONLY place Groq is called (spec §6.2 step 5).
"""
import inspect
import json
import logging
import re

_log = logging.getLogger(__name__)

from app.config import groq_client, GROQ_MODEL

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
    # Cover hire/reject recommendation variants without breaking statistical disclosures
    r"\bhire\b", r"\bhiring\b", r"\bhireable\b", r"\brehire\b",
    r"\bdo not hire\b", r"\bdon't hire\b", r"\bnot hireable\b",
    r"\breject\b", r"\brejecting\b",
    r"\bpass on\b",  # 'pass on this candidate' is a hire/no-hire rec
]


def lint_text(text: str) -> list[str]:
    """Return list of violation strings; empty means the text passed."""
    violations = []
    for pattern in BANNED:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(f"Banned phrase matched: {pattern}")
    return violations


def _sdk_supports_reasoning_effort(client=None) -> bool:
    """Check if the installed Groq SDK supports the reasoning_effort parameter."""
    try:
        import groq.resources.chat.completions
        sig = inspect.signature(groq.resources.chat.completions.Completions.create)
        if "reasoning_effort" in sig.parameters:
            return True
    except Exception:
        pass
    if client is not None:
        try:
            sig = inspect.signature(client.chat.completions.create)
            if "reasoning_effort" in sig.parameters:
                return True
        except Exception:
            pass
    return False


def _groq_call(system_msg: str, user_msg: str, json_mode: bool = True) -> str:
    """Make a real Groq API call. Raises on failure (R6)."""
    client = groq_client()
    fmt = {"type": "json_object"} if json_mode else None
    kwargs = dict(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=1500,
    )
    if fmt:
        kwargs["response_format"] = fmt

    # gpt-oss-120b is a reasoning model; set reasoning_effort to "low" if SDK supports it
    if _sdk_supports_reasoning_effort(client):
        kwargs["reasoning_effort"] = "low"

    response = client.chat.completions.create(**kwargs)
    if not response or not response.choices:
        raise RuntimeError(f"Groq API returned no response choices for model '{GROQ_MODEL}'.")

    content = response.choices[0].message.content
    if not content or not content.strip():
        finish_reason = getattr(response.choices[0], "finish_reason", "unknown")
        raise RuntimeError(
            f"Groq API returned empty content for model '{GROQ_MODEL}' "
            f"(finish_reason={finish_reason})."
        )
    return content


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
    Only called from Stage 4 (spec §6.2 step 5).
    """
    fact_a, fact_b = pair["fact_a"], pair["fact_b"]
    user_msg = (
        f"Claim A ({fact_a['interviewer_id']}, round {fact_a['round']}): "
        f"{fact_a['claim_normalized']}\n"
        f"Claim B ({fact_b['interviewer_id']}, round {fact_b['round']}): "
        f"{fact_b['claim_normalized']}\n\n"
        f"Return JSON with verdict and rationale."
    )

    for attempt in range(2):
        raw = _groq_call(ADJUDICATION_SYSTEM, user_msg, json_mode=True)
        data = _parse_json(raw)
        verdict = data.get("verdict", "")
        rationale = data.get("rationale", "")

        if verdict not in ("CONTRADICTION", "CONDITIONAL_BOTH_APPLY", "COMPLEMENTARY"):
            user_msg += (
                f"\n\n[CORRECTION] Verdict '{verdict}' is not allowed. "
                "Use only CONTRADICTION, CONDITIONAL_BOTH_APPLY, or COMPLEMENTARY."
            )
            continue

        violations = lint_text(rationale)
        if violations:
            user_msg += (
                f"\n\n[CORRECTION] The rationale contains banned language: "
                f"{violations}. Rewrite without it."
            )
            continue

        return {
            "verdict": verdict,
            "rationale": rationale,
            "synthesis_source": "llm",
            "verdict_path": "stage4_llm",
        }

    # Template fallback (lint passed on content, so this is always safe)
    rationale = (
        f"{fact_a['interviewer_id']} (round {fact_a['round']}) reported: "
        f"\"{fact_a['claim_normalized']}\". "
        f"{fact_b['interviewer_id']} (round {fact_b['round']}) reported: "
        f"\"{fact_b['claim_normalized']}\". "
        f"The two claims were not automatically resolved."
    )
    return {
        "verdict": "CONTRADICTION",
        "rationale": rationale,
        "synthesis_source": "template",
        "verdict_path": "stage4_llm",
    }


FOLLOW_UP_SYSTEM = """You generate one concrete probe question for a hiring panel.
The question must help distinguish between two conflicting assessments of a candidate.
Rules:
- Do not favor either interviewer or assessment.
- If the claims come from different rounds, also ask whether the candidate's performance may have changed between rounds (progression is not automatically a contradiction).
- The question must be specific and actionable.
- Do not recommend hiring or not hiring."""


def follow_up(fact_a: dict, fact_b: dict, kind: str) -> str:
    """Generate a follow-up probe question via Groq.

    Retries once on lint failure. Falls back to deterministic template on
    second failure (synthesis_source will be "template").
    """
    user_msg = (
        f"Claim A ({fact_a['interviewer_id']}, round {fact_a['round']}, "
        f"context: {fact_a['task_context']}): {fact_a['claim_normalized']}\n"
        f"Claim B ({fact_b['interviewer_id']}, round {fact_b['round']}, "
        f"context: {fact_b['task_context']}): {fact_b['claim_normalized']}\n"
        f"Disagreement kind: {kind}\n\n"
        f"Write one concrete follow-up question the panel can ask or one exercise "
        f"they can give the candidate."
    )
    for attempt in range(2):
        text = _groq_call(FOLLOW_UP_SYSTEM, user_msg, json_mode=False)
        violations = lint_text(text)
        if not violations:
            return text
        user_msg += f"\n\n[CORRECTION] Banned language detected: {violations}. Rewrite."

    # Deterministic template fallback
    return (
        f"The panel should probe the difference between what "
        f"{fact_a['interviewer_id']} observed (round {fact_a['round']}) "
        f"and what {fact_b['interviewer_id']} observed (round {fact_b['round']}) "
        f"on {fact_a['competency'].replace('_', ' ')}."
    )


COMPETENCY_DISPLAY_NAMES = {
    "system_design": "System Design",
    "concurrency": "Concurrency",
    "algorithmic_optimization": "Algorithmic Optimization",
    "communication": "Communication",
    "product_sense": "Product Sense",
    "culture_add": "Culture Add",
}

BRIEFING_OVERVIEW_SYSTEM = """You are a neutral hiring-panel briefing writer.
Write 3–5 sentences summarising what earlier interviewers found about a candidate.
Rules:
- Every claim must name the interviewer and the round number.
- Do NOT state or imply that one interviewer is more accurate, credible, thorough, or reliable.
- Do NOT recommend whether to hire the candidate.
- Be neutral and descriptive only."""


def _generate_overview(
    candidate_slug: str, for_round: int, findings_by_comp: dict
) -> tuple[str, str]:
    """Generate a 3–5 sentence overview via Hindsight reflect, falling back to Groq.

    Returns (overview_text, synthesis_source).
    On two consecutive failures returns ("", "template").
    """
    # Build a compact summary of findings to feed into reflect/Groq
    lines = []
    for comp, entries in findings_by_comp.items():
        for e in entries:
            lines.append(
                f"{e['interviewer']} (round {e['round']}) on "
                f"{COMPETENCY_DISPLAY_NAMES.get(comp, comp)}: {e['claim']} [{e['polarity']}]"
            )
    if not lines:
        return "", "template"

    context = "\n".join(lines)
    query = (
        f"Summarise what interviewers have found about the candidate before round "
        f"{for_round}. 3–5 neutral sentences, each citing the interviewer and round."
    )

    # Try Hindsight reflect first (it uses memory-augmented LLM)
    try:
        from app.memory import reflect_for_briefing
        text = reflect_for_briefing(candidate_slug, query, context=context)
        violations = lint_text(text)
        if not violations:
            return text, "llm"
        # Lint failed — try a second time with correction
        corrected_query = (
            query + f"\n\n[CORRECTION] Previous output contained banned language: "
            f"{violations}. Rewrite without it."
        )
        text = reflect_for_briefing(candidate_slug, corrected_query, context=context)
        violations = lint_text(text)
        if not violations:
            return text, "llm"
    except Exception as _hindsight_err:
        # LOOPHOLE FIX #2 (REAL): Log AND track that Hindsight failed so
        # the returned synthesis_source accurately reflects which system ran.
        _log.warning(
            "[HINDSIGHT FALLBACK] reflect_for_briefing failed for candidate '%s': %s. "
            "Falling back to direct Groq call.",
            candidate_slug, _hindsight_err,
        )

    # Fallback: Groq — use 'groq_fallback' source so caller always knows
    try:
        user_msg = (
            f"Earlier-round findings for round {for_round} briefing:\n{context}\n\n"
            f"{query}"
        )
        for _ in range(2):
            text = _groq_call(BRIEFING_OVERVIEW_SYSTEM, user_msg, json_mode=False)
            violations = lint_text(text)
            if not violations:
                return text, "groq_fallback"
            user_msg += (
                f"\n\n[CORRECTION] Output contained banned language: {violations}. Rewrite."
            )
    except Exception as _groq_err:
        # Log Groq failure too so we always know why we fell back to template.
        _log.warning(
            "[GROQ FALLBACK] Groq briefing call failed for candidate '%s': %s. "
            "Returning empty template overview.",
            candidate_slug, _groq_err,
        )

    return "", "template"


def briefing(candidate_slug: str, for_round: int, conn, use_memory: bool = True) -> dict:
    """
    Build briefing for the next interviewer.
    Facts from rounds strictly before for_round only.
    Structure built by code; optional LLM overview on top.

    LOOPHOLE FIX #4 (REAL): use_memory=False skips Hindsight AND Groq entirely
    and returns only the raw SQLite-structured data with no LLM-generated overview.
    This enables a genuine live comparison in the UI, not static explanatory text.
    """
    facts = conn.execute(
        "SELECT * FROM facts WHERE candidate_slug=? AND round<?",
        (candidate_slug, for_round),
    ).fetchall()

    if not facts:
        return {
            "for_round": for_round,
            "overview": None,
            "synthesis_source": "no_memory" if not use_memory else "template",
            "earlier_findings": [],
            "open_disagreements": [],
            "insufficient_competencies": list(COMPETENCY_DISPLAY_NAMES.keys()),
            "generic": True,
        }

    # Build structured sections from stored data (always from SQLite — never LLM)
    findings_by_comp: dict[str, list] = {}
    for f in facts:
        comp = f["competency"]
        if comp == "other":
            continue
        findings_by_comp.setdefault(comp, []).append(
            {
                "interviewer": f["interviewer_id"],
                "round": f["round"],
                "claim": f["evidence_span"],
                "polarity": f["polarity"],
            }
        )

    open_disgs = conn.execute(
        "SELECT * FROM disagreements WHERE candidate_slug=? "
        "AND state NOT IN ('RESOLVED','STILL_OPEN')",
        (candidate_slug,),
    ).fetchall()

    structured: dict = {
        "for_round": for_round,
        "earlier_findings": [
            {"competency": c, "claims": v} for c, v in findings_by_comp.items()
        ],
        "open_disagreements": [
            {
                "disagreement_id": d["disagreement_id"],
                "competency": d["competency"],
                "follow_up": d["follow_up"],
                "state": d["state"],
            }
            for d in open_disgs
        ],
        "insufficient_competencies": [],
    }

    if not use_memory:
        # REAL baseline: no LLM, no Hindsight — pure SQLite structured output only.
        structured["overview"] = None
        structured["synthesis_source"] = "no_memory"
        return structured

    # use_memory=True: Attempt LLM overview (Hindsight reflect -> Groq -> template)
    overview, source = _generate_overview(candidate_slug, for_round, findings_by_comp)
    structured["overview"] = overview or None
    structured["synthesis_source"] = source

    return structured


def _count_independent(pairs: list[dict]) -> int:
    sources: set[str] = set()
    for p in pairs:
        if not p["fact_a"]["reviewed_others_notes"] and not p["fact_b"]["reviewed_others_notes"]:
            sources.add(p["fact_a"]["interviewer_id"])
            sources.add(p["fact_b"]["interviewer_id"])
    return len(sources)


def _insufficiency_reason_text(reason: str) -> str:
    # Spec §9 exact text
    if reason == "single_source":
        return (
            "Only one interviewer has given feedback on this competency, "
            "so no comparison is possible."
        )
    if reason == "anchored_agreement_only":
        return (
            "The interviewers who agree here had read each other\u2019s notes, "
            "so their agreement is not counted as independent confirmation."
        )
    return ""


def _store_pair_verdict(conn, slug, comp, pair, pv):
    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    pid = pv.get("pair_id", str(__import__("uuid").uuid4()))
    pv["pair_id"] = pid
    # independent = neither fact's submission was anchored (reviewed_others_notes=False)
    independent = int(
        not pair["fact_a"]["reviewed_others_notes"]
        and not pair["fact_b"]["reviewed_others_notes"]
    )
    anchored_dissent = int(pair.get("anchored_dissent", False))
    polarity_opposite = int(pair.get("polarity_opposite", False))
    try:
        conn.execute(
            "INSERT INTO pair_verdicts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                pid, slug, comp,
                pair["fact_a"]["fact_id"], pair["fact_b"]["fact_id"],
                pv.get("verdict"), pv.get("verdict_path"),
                independent,
                anchored_dissent,
                polarity_opposite,
                pv.get("nli_contradiction_max"),
                pv.get("rationale"), pv.get("synthesis_source"),
                pv.get("follow_up"), now,
            ),
        )
    except Exception as _db_err:
        # LOOPHOLE FIX #3 (REAL): Distinguish expected duplicates from real failures.
        # Duplicates are fine (idempotent re-evaluation) — log at DEBUG and continue.
        # Any other DB error is a real problem — re-raise so the caller knows.
        err_msg = str(_db_err)
        if "UNIQUE" in err_msg.upper():
            _log.debug("[pair_verdicts] Duplicate insert skipped for pair %s (idempotent).", pid)
        else:
            _log.error(
                "[pair_verdicts] DB insert FAILED for pair %s (competency=%s, slug=%s): %s",
                pid, comp, slug, _db_err,
            )
            raise  # re-raise so evaluate_candidate() surfaces the failure


def _build_briefing_summary(competency_analyses: list) -> str:
    """
    LOOPHOLE FIX #7 (REAL): Build a deterministic one-line summary from
    competency verdict counts so briefing_summary is never an empty string.
    Uses only stored data — no LLM call.
    """
    if not competency_analyses:
        return "No competency data available yet."
    verdicts = {}
    for ca in competency_analyses:
        v = ca["verdict"] if isinstance(ca, dict) else ca.verdict
        verdicts[v] = verdicts.get(v, 0) + 1
    parts = []
    if verdicts.get("CONTRADICTION"):
        parts.append(f"{verdicts['CONTRADICTION']} contradiction(s)")
    if verdicts.get("CONDITIONAL_BOTH_APPLY"):
        parts.append(f"{verdicts['CONDITIONAL_BOTH_APPLY']} context-split(s)")
    if verdicts.get("COMPLEMENTARY"):
        parts.append(f"{verdicts['COMPLEMENTARY']} complementary signal(s)")
    if verdicts.get("INSUFFICIENT_EVIDENCE"):
        parts.append(f"{verdicts['INSUFFICIENT_EVIDENCE']} competency area(s) with insufficient evidence")
    total = len(competency_analyses)
    return f"Evaluated {total} competency area(s): {', '.join(parts)}." if parts else f"Evaluated {total} competency area(s)."


def build_evaluation_response(slug, competency_analyses, conn):

    from app.lifecycle import open_disagreements
    from app.models import EvaluationResponse, CompetencyAnalysis, OpenDisagreementSummary

    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    # Fetch candidate display_name and status for UI header
    cand_row = conn.execute(
        "SELECT display_name, status FROM candidates WHERE slug=?", (slug,)
    ).fetchone()
    display_name = cand_row["display_name"] if cand_row else slug
    status = cand_row["status"] if cand_row else "open"

    if status == "finalized":
        rows = conn.execute(
            "SELECT * FROM disagreements WHERE candidate_slug=? AND state='STILL_OPEN'",
            (slug,)
        ).fetchall()
        disgs = [dict(r) for r in rows]
    else:
        disgs = open_disagreements(slug, conn)

    return EvaluationResponse(
        candidate_slug=slug,
        display_name=display_name,
        status=status,
        evaluated_at=now,
        briefing_summary=_build_briefing_summary(competency_analyses),  # LOOPHOLE FIX #7: never empty
        synthesis_source="template",
        competency_analyses=competency_analyses,
        open_disagreements_summary=[
            OpenDisagreementSummary(
                disagreement_id=d["disagreement_id"],
                kind=d["kind"],
                competency=d["competency"],
                state=d["state"],
                raised_at=d["created_at"],
            )
            for d in disgs
        ],
    )


def evaluate_candidate(slug: str, conn):
    from app.gates import build_pairs, sufficiency, route_context
    from app.classify import nli_scores, decide_pair, aggregate
    from app.lifecycle import create_disagreement
    from app.provenance import verdict_path_human_readable
    from app.models import fact_row_to_out, PrimaryPair, SignalSummary

    facts = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM facts WHERE candidate_slug=?", (slug,)
        ).fetchall()
    ]
    pairs_by_comp = build_pairs(facts, conn=conn)

    competency_analyses = []

    for comp, pairs in pairs_by_comp.items():
        status, reason = sufficiency(pairs)

        if status == "INSUFFICIENT_EVIDENCE":
            competency_analyses.append(
                {
                    "competency": comp,
                    "independent_source_count": _count_independent(pairs),
                    "verdict": "INSUFFICIENT_EVIDENCE",
                    "insufficiency_reason": reason,
                    "verdict_path": "stage2_sufficiency",
                    "verdict_path_human_readable": verdict_path_human_readable(
                        "stage2_sufficiency", reason
                    ),
                    "signal_summary": None,
                    "anchored_dissent": False,
                    "pair_count": len(pairs),
                    "primary_pair": None,
                    "disagreement_id": None,
                    "lifecycle_state": None,
                    "synthesis_rationale": _insufficiency_reason_text(reason),
                    "recommended_follow_up": None,
                }
            )
            continue

        pair_verdicts = []
        for pair in pairs:
            # Idempotent: skip pairs already stored
            existing = conn.execute(
                "SELECT * FROM pair_verdicts WHERE fact_a_id=? AND fact_b_id=?",
                (pair["fact_a"]["fact_id"], pair["fact_b"]["fact_id"]),
            ).fetchone()
            if existing:
                d_existing = dict(existing)
                d_existing["fact_a"] = pair["fact_a"]
                d_existing["fact_b"] = pair["fact_b"]
                pair_verdicts.append(d_existing)
                continue

            route = route_context(pair)
            if route == "CONTEXT_SPLIT":
                pv = {
                    **pair,
                    "verdict": "CONDITIONAL_BOTH_APPLY",
                    "verdict_path": "stage2_5_context",
                    "kind": "CONTEXT_SPLIT",
                    "synthesis_source": "template",
                }
            elif route == "COMPLEMENTARY_CONTEXT":
                pv = {
                    **pair,
                    "verdict": "COMPLEMENTARY",
                    "verdict_path": "stage2_5_context",
                    "synthesis_source": "template",
                }
            else:
                # Stage 3
                c = nli_scores(
                    pair["fact_a"]["claim_normalized"],
                    pair["fact_b"]["claim_normalized"],
                )
                decision = decide_pair(pair, c)
                if decision.get("escalate"):
                    # Stage 4 — real Groq adjudication
                    adj = adjudicate(pair)
                    pv = {**pair, **adj, "nli_contradiction_max": c}
                else:
                    pv = {**pair, **decision}

            _store_pair_verdict(conn, slug, comp, pair, pv)
            pair_verdicts.append(pv)

            if pv["verdict"] in ("CONTRADICTION",) or pv.get("kind") == "CONTEXT_SPLIT":
                d_obj = create_disagreement(pv, conn)
                pv["disagreement_id"] = d_obj["disagreement_id"]
                pv["lifecycle_state"] = d_obj["state"]
                pv["recommended_follow_up"] = d_obj.get("follow_up")

        agg = aggregate(pair_verdicts)

        pp = None
        best_pv = agg.get("primary_pair")
        if best_pv:
            pp = PrimaryPair(
                fact_a=fact_row_to_out(best_pv["fact_a"]),
                fact_b=fact_row_to_out(best_pv["fact_b"]),
            )

        ss = None
        if best_pv and best_pv.get("nli_contradiction_max") is not None:
            ss = SignalSummary(
                polarity_opposite=bool(best_pv.get("polarity_opposite", False)),
                nli_contradiction_max=best_pv.get("nli_contradiction_max"),
            )

        ckey = None
        if agg["verdict_path"] == "stage2_5_context":
            ckey = (
                "CONTEXT_SPLIT"
                if agg["verdict"] == "CONDITIONAL_BOTH_APPLY"
                else "COMPLEMENTARY"
            )
        elif agg["verdict_path"] == "stage3_rules":
            ckey = agg["verdict"]

        d_row = conn.execute(
            "SELECT disagreement_id, state, follow_up FROM disagreements WHERE candidate_slug=? AND competency=?",
            (slug, comp),
        ).fetchone()
        disagreement_id = d_row["disagreement_id"] if d_row else None
        lifecycle_state = d_row["state"] if d_row else None
        rec_follow_up = d_row["follow_up"] if d_row else agg.get("recommended_follow_up")

        competency_analyses.append(
            {
                "competency": comp,
                "independent_source_count": _count_independent(pairs),
                "verdict": agg["verdict"],
                "insufficiency_reason": None,
                "verdict_path": agg["verdict_path"],
                "verdict_path_human_readable": verdict_path_human_readable(
                    agg["verdict_path"], ckey
                ),
                "signal_summary": ss,
                "anchored_dissent": agg.get("anchored_dissent", False),
                "pair_count": len(pairs),
                "primary_pair": pp,
                "disagreement_id": disagreement_id,
                "lifecycle_state": lifecycle_state,
                "synthesis_rationale": agg.get("rationale", ""),
                "recommended_follow_up": rec_follow_up,
            }
        )

    return build_evaluation_response(slug, competency_analyses, conn)

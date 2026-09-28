---
phase: 5
title: Stage 4 — Synthesis, Guards, Provenance, Briefing
status: not_started
wave_count: 2
estimated_minutes: 60
depends_on: [phase-4]
---

# Phase 5 Plan — Synthesis, Guards, Provenance, Briefing

## Goal
LLM-powered adjudication with hard lint guards. Static provenance map. Idempotent `evaluate_candidate()`. Briefing built from Hindsight memory.

## Pre-conditions
- Phase 4 CHECKPOINT B passed
- Phase 2: memory.py and ingest.py complete
- DECISIONS.md: Groq mode and Hindsight reflect LLM documented

---

## Wave 1 — `app/provenance.py` (no deps, pure static map)

### Task 5.1 — Static verdict path → human text map

```python
# provenance.py
# Static map. Never call an LLM here.

_PATH_MAP = {
    ("stage2_sufficiency", "single_source"):
        "Not enough independent sources: only one interviewer has assessed this competency.",
    ("stage2_sufficiency", "anchored_agreement_only"):
        "Not enough independent sources: the matching assessments were written after reading each other's notes.",
    ("stage2_5_context", "CONTEXT_SPLIT"):
        "Routed automatically: the two assessments come from different task contexts, so this is tracked as a context split, not a contradiction.",
    ("stage2_5_context", "COMPLEMENTARY"):
        "Routed automatically: different task contexts with consistent assessments.",
    ("stage3_rules", "CONTRADICTION"):
        "Both signals agree: the assessments have opposite polarity and the pattern classifier flags a conflict.",
    ("stage3_rules", "COMPLEMENTARY"):
        "No conflict signals: the assessments are consistent or cover different aspects.",
    ("stage4_llm", None):
        "Signals were mixed, so an AI adjudicated between the three allowed verdicts. Flagged for extra scrutiny.",
}

def verdict_path_human_readable(verdict_path: str, context_key: str | None = None) -> str:
    """
    context_key: the insufficiency reason or verdict for disambiguation.
    For stage4_llm: context_key is ignored.
    """
    if verdict_path == "stage4_llm":
        return _PATH_MAP[("stage4_llm", None)]
    key = (verdict_path, context_key)
    if key not in _PATH_MAP:
        raise ValueError(f"Unknown provenance key: {key}")
    return _PATH_MAP[key]
```

---

## Wave 2 — `app/synthesis.py` (LLM calls + lint guard)

### Task 5.2 — `lint_text(text: str) → list[str]`

Returns list of violations. Empty list = passes.

**Banned patterns (case-insensitive):**
```python
BANNED = [
    r"\bwas right\b", r"\bwas wrong\b",
    r"\bmore accurate\b", r"\bless accurate\b",
    r"\bmore thorough\b", r"\bless thorough\b",
    r"\bmore credible\b", r"\bless credible\b",
    r"\bmore reliable\b", r"\bless reliable\b",
    r"\bstronger assessment\b", r"\bweaker assessment\b",
    r"\bbetter judgment\b", r"\bworse judgment\b",
    r"\bshould be trusted\b",
    r"\bmore likely correct\b", r"\bis probably correct\b",
    r"\bappears more\b", r"\bseems more\b",
    r"\bappears less\b", r"\bseems less\b",
    r"\bbetter interviewer\b", r"\bworse interviewer\b",
    r"\bmore reliable interviewer\b",
    r"\bhire\b", r"\bdo not hire\b", r"\breject\b",  # hire/no-hire recs
]

def lint_text(text: str) -> list[str]:
    import re
    violations = []
    for pattern in BANNED:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(f"Banned phrase matched: {pattern}")
    return violations
```

### Task 5.3 — `adjudicate(pair: dict) → dict`

```python
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
        raw = _groq_call(ADJUDICATION_SYSTEM, user_msg)
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
```

### Task 5.4 — `follow_up(disagreement: dict) → str`

```python
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
```

### Task 5.5 — `briefing(candidate_slug: str, for_round: int, conn) → dict`

```python
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
                                 "follow_up": d["follow_up"], "state": d["state"]} for d in open_disgs],
        "insufficient_competencies": [],
    }

    # 3. Attempt LLM overview (via Hindsight reflect or Groq)
    # Check DECISIONS.md: if reflect is available, use it; else Groq
    overview, source = _generate_overview(candidate_slug, for_round, findings_by_comp)
    structured["overview"] = overview
    structured["synthesis_source"] = source

    return structured
```

### Task 5.6 — `evaluate_candidate(slug: str, conn) → EvaluationResponse`

Idempotent orchestrator connecting all stages:

```python
def evaluate_candidate(slug: str, conn) -> dict:
    from app.gates import build_pairs, sufficiency, route_context
    from app.classify import nli_scores, decide_pair, aggregate
    from app.lifecycle import create_disagreement
    from app.provenance import verdict_path_human_readable

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
        # ... build full CompetencyAnalysis ...

    return build_evaluation_response(slug, competency_analyses, conn)
```

---

## Tests for Phase 5

File: `tests/test_synthesis.py`

```python
from app.synthesis import lint_text
from app.provenance import verdict_path_human_readable

# Phrases that MUST fail lint
MUST_FAIL = [
    "Alice was right about the design",
    "Bob appears more thorough in his assessment",
    "Interviewer A seems more reliable",
    "Claim A is more accurate",
    "The panel should trust Bob's assessment",
    "Alice is more likely correct",
    "Bob showed stronger assessment skills",
    "We should hire the candidate",
]

# Phrases that MUST pass lint
MUST_PASS = [
    "Alice (round 1) described the design as lacking a scaling discussion.",
    "Bob (round 2) reported excellent system design with sharding proposed.",
    "The two assessments differ on the topic of scaling.",
]

def test_lint_fails_banned_phrases():
    for phrase in MUST_FAIL:
        violations = lint_text(phrase)
        assert violations, f"Expected lint to FAIL for: '{phrase}'"

def test_lint_passes_neutral_phrases():
    for phrase in MUST_PASS:
        violations = lint_text(phrase)
        assert not violations, f"Expected lint to PASS for: '{phrase}', got: {violations}"

def test_provenance_map_complete():
    keys = [
        ("stage2_sufficiency", "single_source"),
        ("stage2_sufficiency", "anchored_agreement_only"),
        ("stage2_5_context", "CONTEXT_SPLIT"),
        ("stage2_5_context", "COMPLEMENTARY"),
        ("stage3_rules", "CONTRADICTION"),
        ("stage3_rules", "COMPLEMENTARY"),
        ("stage4_llm", None),
    ]
    for verdict_path, ctx in keys:
        text = verdict_path_human_readable(verdict_path, ctx)
        assert isinstance(text, str) and len(text) > 10
        violations = lint_text(text)
        assert not violations, f"Provenance text for {verdict_path}/{ctx} failed lint: {violations}"
```

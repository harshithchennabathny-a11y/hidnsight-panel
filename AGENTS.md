# Panel — Rules for the coding agent (v5)

Read this file at the start of every task. It does not change between parts.
Also read `APPLICATION_SPEC.md` in full at the start of every task. It is the detailed, word-by-word description of the application (concepts, data model, screens, endpoints, exact text, worked example). If the two files disagree, this file wins; report the conflict.

## The application (single definition — this is the only thing we are building)
**Panel** is a web application (React frontend + FastAPI backend) used by a hiring panel to review one candidate across several interview rounds.
It is NOT a scoring tool, NOT a candidate ranker, NOT a resume screener, NOT a chatbot. "Panel" is the product name, not a UI component.

**Users:** interviewers (submit feedback, read briefings) and a hiring coordinator (reviews disagreements, records what happened when a follow-up was asked, finalizes).

**The whole product in six steps:**
1. An interviewer submits written feedback for a candidate, with round number, task context and a "did you read others' notes?" flag.
2. The system splits it into atomic, cited facts (one claim each, tagged by competency and polarity) and stores them (SQLite + Hindsight memory).
3. For each competency it decides: too little independent evidence, or compares claims from different interviewers and assigns one of four verdicts.
4. Every CONTRADICTION or CONTEXT_SPLIT is saved as a **disagreement** with a lifecycle state and a suggested follow-up question.
5. The coordinator records the outcome of the follow-up; the disagreement moves through its lifecycle. On finalize, unresolved ones become STILL_OPEN and stay visible.
6. Before each new round, the next interviewer gets a briefing built from memory of all earlier rounds.

**Main screens:** Submit feedback / Candidate view (briefing + one card per competency) / Disagreements (list, timeline, resolution form, finalize).
**Scope:** small panels, depth over throughput. Hackathon build, one night, synthetic data only.

### Glossary (use these words exactly; do not invent synonyms)
- **fact**: one atomic claim extracted from a submission. **pair**: two facts from different interviewers on the same competency.
- **verdict**: one of the four values in the Verdict enum, per pair and per competency.
- **disagreement**: the stored object for a CONTRADICTION or CONTEXT_SPLIT pair. (Older drafts said "contradiction object". Use `disagreement` everywhere in code, API and UI. The verdict value stays `CONTRADICTION`.)
- **briefing**: short pre-round summary for the next interviewer. **probe / follow-up**: a question the panel can ask to resolve a disagreement.
- **path**: which stage produced a verdict (`verdict_path`).

### Canonical map (do not add, rename or drop items without writing it in DECISIONS.md)
Backend files: `app/` with `enums.py, thresholds.py, db.py, models.py, memory.py, ingest.py, gates.py, classify.py, synthesis.py, provenance.py, lifecycle.py, main.py`. Frontend: `frontend/`. Also `tests/, scripts/, baseline_comparison/, DECISIONS.md, DEMO_NOTES.md`.
API: `GET /candidates`, `POST /submissions`, `GET /candidates/{slug}/evaluation`, `GET /candidates/{slug}/briefing?for_round=N`, `GET /candidates/{slug}/disagreements`, `POST /disagreements/{id}/probe-asked`, `POST /disagreements/{id}/resolution`, `POST /candidates/{slug}/finalize`, and (Part 10 only) `GET /calibration`.

### Anti-hallucination rules for you, the coding agent
- Everything you need is in this file or the current Part. If a name, field, enum value, endpoint or file is not defined here, do not invent it. Use the closest defined item, or record an `OPEN_QUESTION` in `DECISIONS.md` and choose the simplest option consistent with the rules.
- Never invent library APIs. Read the installed package or its docs first (Hindsight, Groq, sentence-transformers, Tailwind/Vite setup).
- Do not add features, endpoints, tables, screens or dependencies that are not specified.
- Precedence if two instructions conflict: `AGENTS.md` rules > the current Part in `BUILD_STEPS.md` > your own judgment. Report the conflict instead of silently picking.
- Before finishing a Part, list what you built and confirm each item exists in the spec. Remove anything that does not.

## Non-negotiable rules
R1. **Disagreement is an object.** Any CONTRADICTION or CONTEXT_SPLIT result becomes a `disagreement` row (one per candidate, competency, unordered interviewer pair and kind, based on that pair's highest-severity fact pair) with a lifecycle and an append-only transition log. It is never a transient field.
R2. **Atomic facts, raw preserved.** Every fact has `evidence_span`, a verbatim substring of the raw submission. Validate this in code (substring check); reject and retry the extraction once on failure.
R3. **SQLite is the source of truth.** Hindsight mirrors it: retain every fact, every lifecycle transition and every resolution note (with metadata: candidate, interviewer, round, competency, fact_id). Banks: `hiring-candidate-{slug}` holds facts, transitions and resolution notes (tag each `type:fact|transition|resolution`); `interviewer-calibration-global` holds outcome records (Part 10 only). Use recall/reflect for briefings. Do not rely on Hindsight for exact enumeration ("all open disagreements" comes from SQLite). Verify Hindsight's real API from the installed `hindsight-client` package and its docs before writing the wrapper. Never guess signatures.
R4. **Gates are pure functions.** Sufficiency, context routing, the decision table and lifecycle transitions take stored data and return results with no network calls. The LLM annotates at ingestion (claims, competency, polarity) and adjudicates only ambiguous pairs, and those outputs are stored and auditable.
R5. **Anti-adjudication.** Never state or imply that one interviewer is more right, thorough, credible or reliable. Enforced by (a) output schemas with no field that could carry a preference, (b) a lint on all generated text (Part 5), (c) tests.
R6. **No fabrication.** If Hindsight, Groq or the NLI model fails, raise a clear error. The only permitted fallback is deterministic template text built from stored facts, labeled `synthesis_source: "template"`. Identical-input caching is allowed.
R7. **Nothing hidden.** Every verdict shows its `verdict_path` in human-readable form, from a static template map, never LLM-written.
R8. **Named constants** live in `thresholds.py` only. They are `PROVISIONAL` until the calibration script (Part 4) has run.
R9. **Synthetic data only**, disclosed in `DEMO_NOTES.md`, including exactly what was pre-seeded and when.
R10. **Out of scope:** auth, multi-tenancy, deployment hardening, anything not in BUILD_STEPS.md.
R11. **LLM:** all Groq calls use `openai/gpt-oss-120b`. If Part 0 shows it does not support the structured output we need, switch to `qwen/qwen3-32b` and record the change in `DECISIONS.md`. Do not mix models.

## Enums (define once in `enums.py`, import everywhere)
- Competency: `system_design`, `concurrency`, `algorithmic_optimization`, `communication`, `product_sense`, `culture_add`, `other`. Facts outside the list are tagged `other` and excluded from verdicts.
- TaskContext: `whiteboard_design`, `live_coding`, `take_home_review`, `pair_programming`, `behavioral`, `system_design_discussion`, `other`.
- Polarity: `positive`, `negative`, `mixed`, `neutral`.
- Verdict: `CONTRADICTION`, `CONDITIONAL_BOTH_APPLY`, `COMPLEMENTARY`, `INSUFFICIENT_EVIDENCE`.
- VerdictPath: `stage2_sufficiency`, `stage2_5_context`, `stage3_rules`, `stage4_llm`.
- DisagreementKind: `CONTRADICTION`, `CONTEXT_SPLIT`.
- LifecycleState: `RAISED`, `PROBE_ASKED`, `RESOLVED`, `ESCALATED`, `STILL_OPEN`.
- ResolutionType: `CONFIRMS_CLAIM_A`, `CONFIRMS_CLAIM_B`, `BOTH_HOLD_UNDER_DIFFERENT_CONTEXT`, `NEW_INFORMATION_UNRESOLVED`, `UNCLEAR`.

## Pipeline
| Stage | Logic | What it does |
|---|---|---|
| 1 Ingestion | LLM (Groq), then validated by code | Decompose submission into atomic facts: `claim_normalized` (self-contained, names candidate and competency), `competency`, `polarity`, `evidence_span`. Store in SQLite, retain to Hindsight. |
| 2 Sufficiency | pure code | Per competency, see below. |
| 2.5 Context routing | pure code | Same context goes to Stage 3. Different context and opposite polarity gives CONTEXT_SPLIT. |
| 3 Pair classification | local NLI + code | NLI both directions + polarity, then decision table. |
| 4 Synthesis | LLM (Groq) + guards | Adjudicate escalated pairs, write follow-up probes, write briefing. Hindsight `reflect` may power the briefing; check which LLM it uses. Do not assume Groq. |
| 4.5 Resolution | pure code | Structured resolution form drives lifecycle transitions. |
| 5 Calibration | code, CUT-FIRST | Outcome-grounded history, shown separately. |

### Stage 2 rules (per competency, on non-`other` facts)
- Pairs are cross-interviewer only. Two facts from the same interviewer never pair. If they differ in polarity, log a `self_revision` note.
- A pair is **independent** if both submissions have `reviewed_others_notes = false`, otherwise **anchored**.
- `INSUFFICIENT_EVIDENCE` with reason `single_source` if fewer than 2 distinct interviewers.
- `INSUFFICIENT_EVIDENCE` with reason `anchored_agreement_only` if every pair is anchored AND same-polarity.
- **Anchored dissent is NOT demoted.** An anchored pair with opposite polarity is eligible and flagged `anchored_dissent = true`, because disagreeing after reading someone's notes is stronger evidence, not weaker.

### Stage 2.5 and Stage 3 decision table
Inputs per eligible pair: `same_context`, `opposite` (one positive and one negative), `c` = max NLI contradiction probability over both directions, using normalized claims.

1. different context AND opposite → `CONDITIONAL_BOTH_APPLY`, kind `CONTEXT_SPLIT`, path `stage2_5_context`. Creates a disagreement with a probe: was it the task format or a real gap?
2. different context AND same polarity → `COMPLEMENTARY`, path `stage2_5_context`.
3. Otherwise (same context, or different context with mixed/neutral polarity):
   - opposite AND `c ≥ NLI_CONTRADICTION_HIGH` → `CONTRADICTION`, path `stage3_rules` (signals agree)
   - opposite AND `c < HIGH` → escalate to Stage 4 (signals split)
   - not opposite AND `c ≥ HIGH` → escalate (signals split)
   - either polarity `mixed` → escalate
   - not opposite AND `LOW ≤ c < HIGH` → escalate
   - not opposite AND `c < NLI_CONTRADICTION_LOW` → `COMPLEMENTARY`, path `stage3_rules`
4. Escalated pairs: LLM returns exactly one of CONTRADICTION / CONDITIONAL_BOTH_APPLY / COMPLEMENTARY plus a rationale, path `stage4_llm`. It never returns INSUFFICIENT_EVIDENCE and never a preference between interviewers.

**Competency verdict** = highest severity across its eligible pairs: CONTRADICTION > CONDITIONAL_BOTH_APPLY > COMPLEMENTARY. `primary_pair` = highest severity, ties broken by most recent round. Cap 15 pairs per competency. Store every pair verdict in `pair_verdicts`.

Provisional constants: `NLI_CONTRADICTION_HIGH = 0.80`, `NLI_CONTRADICTION_LOW = 0.40`.
NLI model: `cross-encoder/nli-deberta-v3-xsmall` via sentence-transformers. Its label order per the model card is `[contradiction, entailment, neutral]`. Assert this from the model config in a test, do not hardcode blindly.

### Lifecycle (allowed transitions only, anything else raises)
- RAISED → PROBE_ASKED | RESOLVED | ESCALATED
- PROBE_ASKED → RESOLVED | ESCALATED
- ESCALATED → PROBE_ASKED | RESOLVED
- any non-RESOLVED → STILL_OPEN, only via `finalize`
- RESOLVED and STILL_OPEN are terminal

Resolution mapping: CONFIRMS_CLAIM_A/B → RESOLVED ("the follow-up response is consistent with claim A/B"). BOTH_HOLD_UNDER_DIFFERENT_CONTEXT → RESOLVED, retro-tag both facts with the new contexts, keeping the old value in `task_context_history`. NEW_INFORMATION_UNRESOLVED and UNCLEAR → ESCALATED. Every transition writes an append-only `transitions` row and a Hindsight retain.

## Output contract
Per candidate evaluation:
```json
{
  "candidate_slug": "str",
  "evaluated_at": "ISO-8601",
  "briefing_summary": "str",
  "synthesis_source": "llm | template",
  "competency_analyses": [{
    "competency": "str",
    "independent_source_count": 0,
    "verdict": "CONTRADICTION | CONDITIONAL_BOTH_APPLY | COMPLEMENTARY | INSUFFICIENT_EVIDENCE",
    "insufficiency_reason": "single_source | anchored_agreement_only | null",
    "verdict_path": "stage2_sufficiency | stage2_5_context | stage3_rules | stage4_llm",
    "verdict_path_human_readable": "str (static template)",
    "signal_summary": {"polarity_opposite": true, "nli_contradiction_max": 0.0} ,
    "anchored_dissent": false,
    "pair_count": 0,
    "primary_pair": {"fact_a": "Fact", "fact_b": "Fact"},
    "disagreement_id": "str | null",
    "lifecycle_state": "LifecycleState | null",
    "synthesis_rationale": "str",
    "recommended_follow_up": "str | null"
  }],
  "open_disagreements_summary": [{"disagreement_id": "str", "kind": "str", "competency": "str", "state": "str", "raised_at": "ISO-8601"}]
}
```
`primary_pair`, `signal_summary` and `disagreement_id` are null for INSUFFICIENT_EVIDENCE. There is no `confidence_score`. NLI probabilities appear only as raw `signal_summary` diagnostics, never labeled as confidence.
Fact = `{fact_id, claim_raw (the evidence_span), claim_normalized, interviewer, round (int), task_context, reviewed_others_notes, polarity}`.
Calibration output, if built, is a separate endpoint and never embedded in a competency card.

## Working agreement
1. Before each part: state a short plan (files to create or change), then build.
2. Stop at the end of every part, run its acceptance checks, and report pass/fail with evidence. Do not start the next part.
3. If something blocks you, use the documented default and note it in `DECISIONS.md`. Ask a question only if you truly cannot proceed.
4. Tests: `pytest -m "not live"` must pass offline. Tests that call Hindsight, Groq or NLI are marked `live`.
5. Keep code plain and small. Backend: FastAPI, pydantic, sqlite3/SQLAlchemy, sentence-transformers, hindsight-client, groq (or openai-compatible client), pytest. Frontend: Vite + React + Tailwind CSS, using `fetch`, `useState`/`useEffect` and simple tab state. No state library, no UI kit and no router unless truly needed.
6. UI fairness rule: Claim A and Claim B are always rendered with identical size, weight and color, side by side. Verdict colors are used only on the verdict badge, never on a claim or an interviewer name. Nothing in the UI may visually favor one side.

# Panel — Application Specification (v5)

Read this file fully at the start of every task, together with `AGENTS.md`.
`AGENTS.md` holds the rules. This file is the detailed description of the application: what it is, what every part does, what data it holds, what each screen and endpoint does, and one complete worked example.
If this file and `AGENTS.md` disagree, `AGENTS.md` wins. Report the conflict.
Every value in the worked example (Section 12) is illustrative. Never hardcode it.

---

## 1. What Panel is, in plain words

Panel is a web application. A hiring panel uses it to review one candidate at a time across several interview rounds.

Each interviewer writes free-text feedback about the candidate after their interview. Panel keeps all of that feedback in memory, breaks it into single claims, and compares what different interviewers said about the same skill. When two interviewers disagree about the same skill, Panel does not average the disagreement away and does not decide who is right. It saves the disagreement as its own item, suggests a question the panel can ask to resolve it, tracks what happens to it, and keeps it visible until it is resolved or the hiring decision is finalized.

Panel also gives the next interviewer a briefing before their round, built from everything earlier interviewers said.

Panel is NOT: a scoring tool, a ranking tool, a resume screener, a candidate-fit predictor, a chatbot, or a tool that recommends hire or no-hire. It never outputs a single overall number or grade for a candidate. "Panel" is the product name only. It is not a UI component name.

## 2. The problem it solves

In a normal hiring process, each interviewer submits notes alone. At the debrief, people skim each other's notes and the disagreements get averaged into a general feeling ("mixed feedback"). A real disagreement between two qualified people on the same skill is exactly the thing the panel should investigate, and it is usually the thing that disappears. Panel exists to stop that.

Panel is designed for small panels (2–6 interviewers) and final rounds, where depth matters more than throughput.

## 3. Who uses it

There is no login. Two roles exist as ways of using the screens, not as accounts.

- **Interviewer.** Submits feedback for a candidate they interviewed. Reads the briefing for the round they are about to conduct.
- **Coordinator.** Reads the candidate view, sees every disagreement, records what happened when a follow-up question was asked, and finalizes the candidate at decision time.

The Submit form asks for an `interviewer_id` and a display name typed by the user. That is the whole identity model.

## 4. Core concepts (exact definitions)

- **Candidate.** One person being interviewed. Identified by a `slug` (lowercase letters, digits, hyphens; e.g. `meera-rao`) and a display name. Created automatically by the first submission for that slug. Has a status: `open` or `finalized`.
- **Round.** An integer 1–10. Several interviewers can share one round.
- **Submission.** One interviewer's written feedback for one candidate in one round. One submission per (candidate, interviewer, round). A second attempt is rejected.
- **Task context.** What the interviewer and candidate were doing. Fixed dropdown, required, never inferred: `whiteboard_design`, `live_coding`, `take_home_review`, `pair_programming`, `behavioral`, `system_design_discussion`, `other`.
- **reviewed_others_notes.** A required checkbox the interviewer answers at submission time: "I read other interviewers' notes on this candidate before writing this." If true, the submission is called **anchored**. If false, it is **independent**.
- **Fact.** One single claim extracted from a submission. Each fact has: a normalized claim (a self-contained sentence naming the candidate and the competency), an `evidence_span` (the exact words from the raw text that support it), a competency, and a polarity.
- **Competency.** One of: `system_design`, `concurrency`, `algorithmic_optimization`, `communication`, `product_sense`, `culture_add`, `other`. Facts that fit none are tagged `other` and are excluded from all comparisons and verdicts.
- **Polarity.** `positive`, `negative`, `mixed`, or `neutral`. The direction of the claim about the candidate on that competency. Assigned once, at ingestion, and stored.
- **Pair.** Two facts, on the same competency, from two different interviewers. Two facts from the same interviewer never form a pair.
- **Verdict.** `CONTRADICTION`, `CONDITIONAL_BOTH_APPLY`, `COMPLEMENTARY`, or `INSUFFICIENT_EVIDENCE`. Meanings:
  - CONTRADICTION: two independent interviewers made opposing claims about the same skill in the same task context. It needs investigation.
  - CONDITIONAL_BOTH_APPLY: both claims can be true because the conditions differ (for example different task contexts). It is still tracked.
  - COMPLEMENTARY: the claims agree or cover different aspects of the same skill. No conflict.
  - INSUFFICIENT_EVIDENCE: fewer than two independent sources exist for that competency, so no comparison is made.
- **Disagreement.** A stored item created for every pair that is a CONTRADICTION, or a CONDITIONAL_BOTH_APPLY caused by opposing polarity across different task contexts (called a **CONTEXT_SPLIT**). It has a kind (`CONTRADICTION` or `CONTEXT_SPLIT`), a lifecycle state, a suggested follow-up question, and a full transition history.
- **Lifecycle state.** `RAISED` (detected, probe not yet asked), `PROBE_ASKED` (the panel has been given the follow-up question), `RESOLVED`, `ESCALATED` (resolution surfaced new unresolved information), `STILL_OPEN` (nothing resolved it before finalization).
- **Probe / follow-up.** One concrete question or exercise the panel can use to distinguish between the two claims.
- **Resolution.** A record of what happened when the probe was asked, entered by the coordinator through a structured form.
- **Briefing.** A short pre-round summary for the next interviewer.
- **Finalize.** The coordinator's action that closes a candidate. All unresolved disagreements become STILL_OPEN and stay visible in the final summary.
- **Path.** Which processing stage decided a verdict (`verdict_path`). Always shown to the user in plain language.

## 5. Data model (SQLite, the source of truth)

Create these tables exactly. Add columns only if you record the reason in `DECISIONS.md`.

**candidates**: `slug` (PK), `display_name`, `status` (`open`|`finalized`, default `open`), `created_at`, `finalized_at` (null until finalized).

**submissions**: `submission_id` (PK), `candidate_slug` (FK), `interviewer_id`, `interviewer_name`, `round` (int), `task_context`, `reviewed_others_notes` (bool), `raw_text`, `created_at`. UNIQUE(`candidate_slug`, `interviewer_id`, `round`).

**facts**: `fact_id` (PK), `submission_id` (FK), `candidate_slug`, `interviewer_id`, `round`, `claim_normalized`, `evidence_span`, `competency`, `polarity`, `task_context` (current value), `task_context_history` (JSON list of earlier values, default `[]`), `reviewed_others_notes` (copied from the submission), `mirrored` (bool, default false), `created_at`.

**pair_verdicts**: `pair_id` (PK), `candidate_slug`, `competency`, `fact_a_id`, `fact_b_id`, `verdict`, `verdict_path`, `independent` (bool), `anchored_dissent` (bool), `polarity_opposite` (bool), `nli_contradiction_max` (real, null if NLI was not run), `rationale`, `synthesis_source` (`llm`|`template`), `follow_up` (null unless disagreement), `evaluated_at`. UNIQUE(`fact_a_id`, `fact_b_id`).

**disagreements**: `disagreement_id` (PK), `candidate_slug`, `competency`, `kind`, `interviewer_a_id`, `interviewer_b_id` (the two interviewer ids, sorted alphabetically), `fact_a_id`, `fact_b_id`, `pair_id` (FK), `state`, `follow_up`, `created_at`, `updated_at`. UNIQUE(`candidate_slug`, `competency`, `interviewer_a_id`, `interviewer_b_id`, `kind`).
One disagreement exists per competency and pair of interviewers, even if those two interviewers have several facts on that competency. The disagreement points at the highest-severity fact pair (ties: most recent round) as of when it was created, and is not replaced later.

**transitions** (append-only, never updated or deleted): `transition_id` (PK), `disagreement_id`, `from_state` (null for the first), `to_state`, `note`, `created_at`.

**resolutions**: `resolution_id` (PK), `disagreement_id`, `resolution_type`, `note`, `context_a` (null unless BOTH_HOLD_UNDER_DIFFERENT_CONTEXT), `context_b` (same), `created_at`.

**evaluation_notes**: `note_id` (PK), `candidate_slug`, `competency`, `type` (currently only `self_revision`), `detail`, `created_at`.

**outcomes** (Part 10 only): `outcome_id` (PK), `candidate_slug`, `interviewer_id`, `competency`, `rated_negative` (bool), `outcome` (`positive`|`negative`), `synthetic` (bool, default true).

**Ordering rule for A and B.** In every pair, `fact_a` is the fact from the earlier round. If the rounds are equal, `fact_a` is the one whose `interviewer_id` sorts first alphabetically. This rule is applied everywhere so "Claim A" and "Claim B" are always the same two facts in the same positions. It has no meaning beyond ordering.

## 6. How processing works, step by step

### 6.1 When a submission arrives (`POST /submissions`)
1. Validate the request (Section 8). Reject invalid ones with a clear error. Reject if the candidate is finalized.
2. Create the candidate if the slug is new.
3. **Extract facts (LLM, Groq).** One call with a JSON schema returns a list of facts: `claim_normalized`, `competency`, `polarity`, `evidence_span`. Instructions to the model: one claim per fact, each claim self-contained (name the candidate and the competency so NLI can classify it standalone), use only what the text says, do not infer or add anything.
4. **Validate in code.** Every `evidence_span` must be a verbatim substring of `raw_text`. If any fail, retry once, quoting the failures back. If they fail again, return a 502 with a clear message. Nothing is stored.
5. **Store.** In one SQLite transaction, insert the submission and its facts.
6. **Mirror to Hindsight.** Retain each fact to bank `hiring-candidate-{slug}` with metadata (candidate, interviewer, round, competency, fact_id, tag `type:fact`). Set `mirrored = true` for each success. If a retain fails, return 502 with the submission_id and the unmirrored fact ids. The data stays in SQLite. `scripts/remirror.py` retries every fact where `mirrored = false`.
7. **Evaluate** every competency touched by the new facts (Section 6.2). Return the submission, its facts, and the affected competency analyses.

### 6.2 Evaluating a competency (deterministic order)
1. Take all facts for the candidate and competency (not `other`).
2. **Stage 2, sufficiency.** Count distinct interviewers. Fewer than 2 → `INSUFFICIENT_EVIDENCE`, reason `single_source`, path `stage2_sufficiency`. Stop. Otherwise build all cross-interviewer pairs (cap 15; if more, keep the 15 with the most recent rounds). Record a `self_revision` note when one interviewer's facts differ in polarity. If every pair is anchored and same-polarity → `INSUFFICIENT_EVIDENCE`, reason `anchored_agreement_only`. Stop. Anchored pairs with opposite polarity stay eligible and get `anchored_dissent = true`.
3. **Stage 2.5, context routing.** Per pair, apply the decision-table rules 1 and 2 in `AGENTS.md`.
4. **Stage 3, classification.** For the remaining pairs, run the NLI model in both directions on the two normalized claims, take the maximum contradiction probability, and apply the decision table. Some pairs are decided; some are escalated.
5. **Stage 4, adjudication.** Escalated pairs go to the LLM, which must return exactly one of CONTRADICTION, CONDITIONAL_BOTH_APPLY, COMPLEMENTARY plus a rationale. Every generated rationale passes the lint (Section 10).
6. **Aggregate.** Competency verdict = highest severity among its pair verdicts (CONTRADICTION > CONDITIONAL_BOTH_APPLY > COMPLEMENTARY). The pair that set that verdict is the `primary_pair`; ties are broken by the most recent round.
7. **Persist.** Save pair verdicts (skip any pair that already has one, so LLM calls are never repeated). For every pair that is a CONTRADICTION or CONTEXT_SPLIT, create a disagreement (idempotent per the unique key in Section 5, so several fact pairs between the same two interviewers on one competency give one disagreement), state `RAISED`, with a follow-up question. Write a transition row and retain it to Hindsight (tag `type:transition`).

**Verdicts are historical records.** They are never recomputed after a resolution. After a disagreement is resolved, the competency card still shows its original verdict, with the lifecycle state beside it (for example "CONTRADICTION · Resolved").

### 6.3 Lifecycle and resolution
Allowed transitions and the resolution mapping are in `AGENTS.md`. Any other transition raises `InvalidTransition` and the API returns 409.
- "Mark probe asked" moves RAISED or ESCALATED to PROBE_ASKED.
- A resolution can be submitted from RAISED, PROBE_ASKED or ESCALATED.
- `BOTH_HOLD_UNDER_DIFFERENT_CONTEXT` requires two contexts. Set each fact's current `task_context` to the given value and append the previous value to its `task_context_history`.
- Every transition writes a `transitions` row and a Hindsight retain. The resolution note is retained as its own fact (tag `type:resolution`) carrying the `disagreement_id`.

### 6.4 Finalize
`POST /candidates/{slug}/finalize` sets the candidate status to `finalized`, moves every disagreement not in RESOLVED to STILL_OPEN (with a transition row each), and returns a final summary: every disagreement with its state, the verdict per competency, and the list of competencies with insufficient evidence. A finalized candidate accepts no more submissions and no more resolutions (409).

### 6.5 Briefing (`GET /candidates/{slug}/briefing?for_round=N`)
Built from facts in rounds strictly before N.
- The structure is built by code from stored data, never by the LLM: (a) "What earlier rounds found" (per competency, each claim with interviewer and round), (b) "Open disagreements to probe" (each with its follow-up question), (c) "Competencies with too little evidence".
- If there are no earlier facts, return the generic form: a template naming the six competencies and stating that no earlier feedback exists.
- On top of the structure, an overview of 3–5 sentences may be written (using Hindsight recall/reflect or the Groq model). It passes the lint. If it fails twice, the overview is omitted and the structured sections are shown alone (`synthesis_source: "template"`).
- The generic briefing after round 1 versus the specific briefing by round 3 is the visible "memory" moment in the demo.

## 7. The screens (React + Tailwind, three tabs)

General: the layout is a top bar with the product name "Panel" and a candidate selector (from `GET /candidates`), then three tabs. Loading and error states are shown for every request. Errors show the message from the API, verbatim.

### 7.1 Submit tab
Fields, in this order, with these labels:
1. "Candidate name" (text) and "Candidate ID" (slug, auto-filled from the name, editable, validated).
2. "Your ID" (text) and "Your name" (text).
3. "Round" (number 1–10).
4. "Task context" (dropdown, the seven values shown as readable labels).
5. Checkbox: "I read other interviewers' notes on this candidate before writing this."
6. "Feedback" (textarea, 20–4000 characters, with a live counter).
Button: "Submit feedback". On success show the extracted facts as a list: each with its competency, polarity and the highlighted evidence span from the original text, so the interviewer can see how their words were interpreted. No editing of facts in v1.

### 7.2 Candidate tab
- Header: candidate name, status chip (Open / Finalized), and a "Briefing for round" selector with the resulting briefing shown below.
- Below the briefing, one **competency card** per competency that has any facts. Each card shows:
  1. Competency name and a **verdict badge** (the only element with verdict color).
  2. The **path line**: `verdict_path_human_readable`, in plain text under the badge. Always visible, never in a tooltip.
  3. "Independent sources: N".
  4. If the verdict is not INSUFFICIENT_EVIDENCE: the **claim pair**, two equal columns labeled "Claim A" and "Claim B". Each column shows the exact words (`claim_raw`, the evidence span), the interviewer name, the round and the task context. Both columns look identical in size, weight and color.
  5. If `anchored_dissent`: the note "One of these assessments was written after reading the other interviewer's notes."
  6. "N pairs compared. The pair shown is the highest-severity one."
  7. The rationale and the follow-up question.
  8. The disagreement's lifecycle chip, if one exists.
  9. A small "diagnostics" line with `nli_contradiction_max` and `polarity_opposite`, labeled as raw signals and not as confidence.
- INSUFFICIENT_EVIDENCE cards show only the badge, the path line and the reason text (Section 9).

### 7.3 Disagreements tab
- A list of every disagreement for the selected candidate, sorted with unresolved first. Each row shows: kind, competency, state chip, raised date.
- Expanding a row shows the **provenance timeline** built from `transitions` (state, time, note) plus the verdict path line of the pair that raised it, both claims (identical styling), and the follow-up question.
- Buttons per state: "Mark probe asked" (RAISED or ESCALATED); "Record resolution" (RAISED, PROBE_ASKED, ESCALATED), which opens the resolution form:
  - "What happened when the follow-up was asked?" (dropdown of the five resolution types, labels in Section 9)
  - two extra dropdowns for the contexts, shown only for BOTH_HOLD_UNDER_DIFFERENT_CONTEXT
  - "Notes" (textarea, at least 10 characters)
- A "Finalize" button at the top with a confirmation dialog: "Finalizing locks this candidate. Disagreements that are not resolved will be recorded as Still open."
- After finalization the tab shows the final summary.

## 8. The API in full (backend, FastAPI)

All request and response bodies are JSON. Validation errors return 400 with `{ "error": "..." }`. Not found returns 404. Conflicts return 409. Failures of Hindsight, Groq or the NLI model return 502 with a clear message and never a fabricated result.

- `GET /candidates` → list of `{slug, display_name, status, round_count, open_disagreement_count}`.
- `POST /submissions`. Body: `{candidate_slug, candidate_name, interviewer_id, interviewer_name, round, task_context, reviewed_others_notes, feedback_text}`. Validation: slug matches `^[a-z0-9]+(-[a-z0-9]+)*$`; round 1–10; task_context in the enum; feedback_text 20–4000 characters; all fields present. 409 if the candidate is finalized or if this interviewer already submitted for this candidate and round. Response: `{submission_id, facts: [Fact], evaluation: [CompetencyAnalysis]}` for the affected competencies.
- `GET /candidates/{slug}/evaluation` → the output contract in `AGENTS.md`, assembled from stored data. No LLM calls except when a stored pair has no rationale yet.
- `GET /candidates/{slug}/briefing?for_round=N` → `{for_round, overview | null, synthesis_source, earlier_findings: [...], open_disagreements: [...], insufficient_competencies: [...]}`.
- `GET /candidates/{slug}/disagreements` → list of disagreements, each with both facts, kind, state, follow_up, and its `transitions`.
- `POST /disagreements/{id}/probe-asked` → updated disagreement. 409 if the transition is not allowed.
- `POST /disagreements/{id}/resolution`. Body: `{resolution_type, note, context_a?, context_b?}`. Notes at least 10 characters. Contexts required and in the enum for BOTH_HOLD_UNDER_DIFFERENT_CONTEXT, forbidden otherwise. Response: updated disagreement.
- `POST /candidates/{slug}/finalize` → the final summary (Section 6.4).
- `GET /calibration` (Part 10 only).

## 9. Exact user-facing text

**Verdict badge labels:** "Contradiction", "Both apply (conditional)", "Complementary", "Insufficient evidence".

**Lifecycle chips:** "Raised", "Probe asked", "Resolved", "Escalated", "Still open".

**Insufficient-evidence reasons:**
- `single_source`: "Only one interviewer has given feedback on this competency, so no comparison is possible."
- `anchored_agreement_only`: "The interviewers who agree here had read each other's notes, so their agreement is not counted as independent confirmation."

**Path lines** (static map keyed on `verdict_path` and, where noted, the outcome; never written by an LLM):
- `stage2_sufficiency`, single_source: "Not enough independent sources: only one interviewer has assessed this competency."
- `stage2_sufficiency`, anchored_agreement_only: "Not enough independent sources: the matching assessments were written after reading each other's notes."
- `stage2_5_context`, CONTEXT_SPLIT: "Routed automatically: the two assessments come from different task contexts, so this is tracked as a context split, not a contradiction."
- `stage2_5_context`, COMPLEMENTARY: "Routed automatically: different task contexts with consistent assessments."
- `stage3_rules`, CONTRADICTION: "Both signals agree: the assessments have opposite polarity and the pattern classifier flags a conflict."
- `stage3_rules`, COMPLEMENTARY: "No conflict signals: the assessments are consistent or cover different aspects."
- `stage4_llm`: "Signals were mixed, so an AI adjudicated between the three allowed verdicts. Flagged for extra scrutiny."

**Resolution type labels** (dropdown):
- CONFIRMS_CLAIM_A: "The follow-up response is consistent with Claim A"
- CONFIRMS_CLAIM_B: "The follow-up response is consistent with Claim B"
- BOTH_HOLD_UNDER_DIFFERENT_CONTEXT: "Both claims hold, under different conditions"
- NEW_INFORMATION_UNRESOLVED: "New information came up that is not yet resolved"
- UNCLEAR: "The response did not clearly settle it"

## 10. Language rules (every generated or template string)

Neutral, descriptive, attributed. Every claim in any generated text names its interviewer and round.
Allowed: "Arjun (round 1) described the design as lacking a scaling discussion. Kavya (round 2) described the same design as handling scale well."
Never allowed, in any string, from anyone: "was right", "was wrong", "more accurate", "more thorough", "more credible", "more reliable", "stronger assessment", "better judgment", "should be trusted", "is probably correct", or any recommendation to hire or not hire.
Never say which interviewer is likely correct, and never rank interviewers.
The lint from Part 5 is applied to every LLM output, every briefing overview, every resolution copy string and every template in a test.

## 11. Things Panel deliberately does not do
No login or accounts. No overall candidate score, grade or ranking. No hire/no-hire recommendation. No editing of extracted facts. No email or calendar integration. No resume parsing. No multi-candidate comparison. No production deployment concerns. No real candidate data: synthetic only.

## 12. Worked example (illustrative, do not hardcode)

Candidate: "Meera Rao", slug `meera-rao`. Three interviewers: `arjun`, `kavya`, `dev`.

**Round 1, Arjun**, `whiteboard_design`, independent. Raw text: "Meera's system design was weak. She jumped straight to a single database and never discussed scaling or failure modes. Her concurrency knowledge was solid; she explained locking clearly. She was hard to follow when explaining her code."
Extracted facts: (1) system_design, negative, "Meera's system design was weak"; (2) system_design, negative, "never discussed scaling or failure modes"; (3) concurrency, positive, "Her concurrency knowledge was solid"; (4) communication, negative, "hard to follow when explaining her code". (Arjun's task context was recorded as `whiteboard_design`, so fact 4 also carries that context.)

**Round 2, Kavya**, `whiteboard_design`, independent. Raw text: "Excellent system design. She proposed sharding early and walked through failure handling step by step. On concurrency she reasoned well about race conditions."
Facts: (5) system_design, positive; (6) concurrency, positive, about race conditions.

**Round 3, Dev**, `behavioral`, independent. Raw text: "Meera communicated very clearly and gave structured answers. She seemed to fit how our team works."
Facts: (7) communication, positive; (8) culture_add, positive.

**What the system decides (after all three):**
- `system_design`: Arjun and Kavya, both independent, same context, opposite polarity. NLI contradiction probability is high (illustratively 0.9, at or above the high threshold), so the decision table gives CONTRADICTION via `stage3_rules`. Arjun has two system_design facts, so two pairs form, and both are CONTRADICTION; still only one disagreement (kind `CONTRADICTION`) is created for Arjun and Kavya on this competency, in state RAISED. Follow-up suggested (illustrative): "Ask Meera to redesign the same service for both 10 thousand and 10 million users, and compare how her handling of scaling and failure changes."
- `concurrency`: both positive, different aspects (locking vs race conditions); NLI contradiction probability low, so COMPLEMENTARY via `stage3_rules`. No disagreement.
- `communication`: Arjun negative in `whiteboard_design`, Dev positive in `behavioral`, opposite polarity, different contexts. Decision table rule 1: CONDITIONAL_BOTH_APPLY, kind CONTEXT_SPLIT, via `stage2_5_context`. A disagreement is created (RAISED). Follow-up (illustrative): "Was the difference the task format, explaining code live versus answering structured questions, or a real communication gap?"
- `culture_add`: only Dev has spoken. INSUFFICIENT_EVIDENCE, `single_source`, via `stage2_sufficiency`.
- `product_sense`, `algorithmic_optimization`: no facts, so no cards.

**Briefings:** for round 1 (before Arjun): generic template, no earlier feedback. For round 2 (before Kavya): Arjun's four findings. For round 3 (before Dev): both earlier rounds, the system_design disagreement with its probe, and the note that concurrency is consistent. This is the "before and after" the demo shows.

**Lifecycle:** the coordinator marks the system_design probe as asked (PROBE_ASKED), asks the redesign question, and records a resolution `BOTH_HOLD_UNDER_DIFFERENT_CONTEXT` with `context_a = system_design_discussion` (Arjun's question was about high scale) and `context_b = whiteboard_design` (illustrative), note "Arjun's question assumed millions of users; Kavya's assumed thousands." The disagreement becomes RESOLVED, both facts are re-tagged and keep their old context in `task_context_history`, and the competency card still reads "Contradiction · Resolved". The communication context split is left untouched. On finalize, it becomes STILL_OPEN and appears in the final summary.

## 13. Definition of done for the whole application
- A user can submit feedback, see the extracted facts, see a verdict card per competency with its path line, see disagreements with a timeline, record a resolution, request a briefing per round, and finalize.
- All four verdicts and both disagreement kinds appear in seeded data.
- No text anywhere states or implies which interviewer is right.
- `pytest -m "not live"` passes.
- `DEMO_NOTES.md` states exactly what is pre-seeded and that all data is synthetic.

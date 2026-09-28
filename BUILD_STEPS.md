# Panel — Build Steps (v5)

How to use: put `AGENTS.md` in the workspace as the rules file, and `APPLICATION_SPEC.md` next to it. Paste **one Part at a time** into Antigravity (paste the whole section). Each Part ends with acceptance checks and a STOP. Review before pasting the next one.

Time-boxes are rough estimates. Tell me your real deadline and I'll convert them into clock times.

## Priority tiers (cut from the bottom)
| Tier | Parts | Note |
|---|---|---|
| MVP core | 0, 1, 2, 3, 4, 5 | Gates, verdicts, grounded synthesis. This is the "not an LLM wrapper" proof. |
| Differentiator | 6 | Disagreement lifecycle. Keep this above everything below. |
| Demo-ready | 7, 8 | UI and seeded demo. Without these there is nothing to show. |
| Hardening | 11 | Retries, cache, recorded backup. |
| Stretch | 9 | Baseline comparison. |
| Cut first | 10 | Calibration. |

Suggested execution order: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 11 → 9 → 10.
Total for the core through Part 8: about 8.5–9.5 hours. Parts 9–11 add about 1.5–2 hours.

---

## PART 0 — Scaffold and smoke tests (30–45 min)

Goal: prove every external dependency works before building anything on it.

Read `AGENTS.md` and `APPLICATION_SPEC.md` fully. Then:
1. Create the repo layout: `app/` (`enums.py`, `thresholds.py`, `db.py`, `models.py`, `memory.py`, `ingest.py`, `gates.py`, `classify.py`, `synthesis.py`, `provenance.py`, `lifecycle.py`, `main.py`), `tests/`, `scripts/`, `baseline_comparison/`, `frontend/`, plus `DECISIONS.md` and `DEMO_NOTES.md` stubs. Add `.env.example` with `HINDSIGHT_*` and `GROQ_API_KEY` placeholders (use whatever variable names the installed clients actually require).
2. Read the installed `hindsight-client` package and its docs. In `DECISIONS.md`, write down the real signatures of retain, recall and reflect, how banks are created, and what metadata/tags are supported. Do not guess.
3. Write `scripts/smoke.py` that: (a) retains one test fact to a scratch bank and recalls it, (b) makes one Groq call using structured output and reports whether JSON-schema output is supported (if not, note the fallback: JSON mode plus pydantic validation plus one retry), (c) loads `cross-encoder/nli-deberta-v3-xsmall`, prints its `id2label` mapping, and classifies one obviously contradicting pair.
4. Scaffold `frontend/` with Vite + React and Tailwind CSS (`npm create vite@latest frontend -- --template react`, then add Tailwind following its current Vite setup docs; check them rather than assuming). Add CORS middleware to FastAPI for the Vite dev origin, and read the API base URL from `VITE_API_URL`.

Acceptance: `python scripts/smoke.py` prints PASS for all three, `npm run build` in `frontend/` succeeds, and `DECISIONS.md` lists the verified Hindsight signatures and Groq structured-output support. If any check fails, report the exact error and STOP.

STOP.

---

## PART 1 — Data model and config (30 min)

Goal: one place for enums, schema and constants.

Build:
- `enums.py` exactly as defined in `AGENTS.md`.
- `thresholds.py` with `NLI_CONTRADICTION_HIGH` and `NLI_CONTRADICTION_LOW` marked `PROVISIONAL`, plus `MAX_PAIRS_PER_COMPETENCY = 15`.
- SQLite schema in `db.py`: create exactly the tables and columns in Section 5 of `APPLICATION_SPEC.md` (`candidates`, `submissions`, `facts`, `pair_verdicts`, `disagreements`, `transitions`, `resolutions`, `evaluation_notes`, and `outcomes` for Part 10), including every UNIQUE constraint.
- Pydantic models matching the output contract in `AGENTS.md`.

Acceptance: `pytest -m "not live"` has tests that create the DB, insert a candidate with two submissions and three facts, and read them back. A test confirms the unique constraint on disagreements prevents duplicates.

STOP.

---

## PART 2 — Stage 1: ingestion and memory (60 min)

Goal: turn a raw submission into validated atomic facts, stored in SQLite and mirrored to Hindsight.

Build:
- `ingest.py`: takes a submission (interviewer_id, candidate_slug, round, task_context, reviewed_others_notes, raw text). One Groq call with a JSON schema returns a list of facts. Each fact has `claim_normalized` (self-contained: it names the candidate and the competency so NLI can classify it standalone), `competency` (enum, `other` if none fits), `polarity`, and `evidence_span`.
- Validate in code that every `evidence_span` is a verbatim substring of the raw text. On failure, retry once with the failing spans quoted back to the model; on second failure, raise.
- `memory.py`: thin wrapper around the verified Hindsight calls. `retain_fact(fact)` with metadata, `recall_for_candidate(slug, query)`. The Hindsight bank per candidate is `hiring-candidate-{slug}`.
- SQLite is written first; the Hindsight retain follows. If the retain fails, raise (502) and don't mark the fact as mirrored (`mirrored` boolean). Also write `scripts/remirror.py`, which retries every fact where `mirrored = false`.
- Follow the exact request validation, error codes and processing order in Sections 6.1 and 8 of `APPLICATION_SPEC.md`.

Acceptance: (offline) unit tests for the span validator with one passing and one failing case, using a mocked LLM. (live) ingest one hand-written 5-sentence feedback covering 3 competencies, show the stored facts with their spans and polarities, and show a recall query returning them.

STOP.

---

## PART 3 — Stage 2 and 2.5: pure-code gates (45 min)

Goal: the sufficiency gate and context routing, fully deterministic and tested.

Build in `gates.py`, as pure functions over lists of stored facts and submissions:
- `build_pairs(facts)`: cross-interviewer pairs per competency (excluding `other`), capped, with `independent` and `anchored_dissent` flags. Same-interviewer differences produce a `self_revision` note, not a pair.
- `sufficiency(competency_pairs)`: returns INSUFFICIENT_EVIDENCE with `single_source` or `anchored_agreement_only`, or "sufficient".
- `route_context(pair)`: implements decision-table rules 1 and 2, or returns "needs_stage3".

Acceptance tests (offline, no mocks needed):
1. One interviewer, two facts → `single_source`
2. Two interviewers, both anchored, same polarity → `anchored_agreement_only`
3. One independent, one anchored, opposite polarity → eligible, `anchored_dissent = true`
4. Two independent interviewers, same context → needs_stage3
5. Different context, opposite polarity → CONTEXT_SPLIT
6. Different context, same polarity → COMPLEMENTARY
7. Same interviewer, different rounds, opposite polarity → no pair, `self_revision` note
8. A fact tagged `other` never appears in a pair

CHECKPOINT A: after these pass, print a short table of the 8 tests and their outputs and STOP. I review before Part 4.

STOP.

---

## PART 4 — Stage 3: pair classification and calibration (60–75 min)

Goal: NLI plus polarity, decision table, competency aggregation, and empirically checked thresholds.

Build:
- `classify.py`: `nli_scores(claim_a, claim_b)` runs the cross-encoder in both directions and returns max contradiction probability. Assert the label order from the model config.
- `decide_pair(pair, c)`: the exact decision table from `AGENTS.md` (rules 3 and 4). Pure function, `c` passed in, so it's testable without the model.
- `aggregate(pair_verdicts)`: severity ordering, `primary_pair`, tie-break by most recent round.
- `scripts/calibrate_nli.py`: reads `fixtures/nli_pairs.jsonl` (label: contradiction | agree | different_facets | hedged) and prints the distribution of `c` per label, then suggests HIGH and LOW. Write at least 24 fixture pairs about hiring feedback covering: obvious contradiction, subtle contradiction, same-meaning paraphrase, different facets of the same competency, hedged or euphemistic disagreement ("could be sharper on tradeoffs" versus "excellent tradeoff reasoning"), and a later-round improvement reported by a different interviewer (label it by your judgment and note that it is ambiguous). Tune on 16 and report accuracy on the 8 held out. Update `thresholds.py` only via the script's output and change the marker from `PROVISIONAL` to a comment citing the run. If time is short, leave the constants `PROVISIONAL` and say so.

Acceptance: offline tests cover every branch of the decision table (each row of rules 3 and 4) using injected `c` values. Live: calibration script runs and prints the per-label distribution and held-out accuracy.

CHECKPOINT B: show the held-out results and any misclassified pairs, then STOP.

STOP.

---

## PART 5 — Stage 4: synthesis, guards, provenance, briefing (60 min)

Goal: grounded text with hard guards against adjudication.

Build in `synthesis.py`:
- `adjudicate(pair)`: Groq structured output returning `{verdict, rationale}` restricted to the three allowed verdicts. The prompt must state the claims neutrally as "Claim A (interviewer, round)" and "Claim B (interviewer, round)" and must forbid any statement about which is more accurate or credible.
- `follow_up(disagreement)`: generate one concrete probe question for the panel that would distinguish the two claims. If the claims come from different rounds, the probe must also cover whether the candidate's performance changed between rounds (progression is not automatically a contradiction).
- `briefing(candidate, for_round)`: recall prior facts via Hindsight for rounds before `for_round` and produce a short briefing for the next interviewer: what earlier interviewers found, what is still open, what to probe. Check which LLM `reflect` uses. If you use reflect, keep the same guards on its output.
- **Guard** `lint_text(text)`: rejects comparatives and credibility language about interviewers or their assessments. Cover at least: right, wrong, correct, incorrect, more/less accurate, more/less thorough, more/less credible, more/less reliable, stronger/weaker assessment, better/worse judgment, "should be trusted", "more likely correct". Also require that every claim sentence carries a fact citation (interviewer + round). On lint failure retry once with the violation quoted; on second failure use a deterministic template built from the stored facts and set `synthesis_source = "template"`.
- `provenance.py`: static template map from (verdict_path, signal state) to human-readable strings. No LLM involvement.
- `evaluate_candidate(slug)` in `main.py` or a service module: runs Stage 2 → 2.5 → 3 → 4 for all competencies and returns the output contract. It is idempotent: re-running does not duplicate pair verdicts or disagreements.

Acceptance: offline tests for `lint_text` (at least 8 phrases that must fail, including "appears more thorough" and "seems more reliable", and 3 neutral sentences that must pass) and for the provenance map. Live: evaluate a seeded candidate and show the JSON.

STOP.

---

## PART 6 — Disagreement lifecycle and resolution (45 min)

Goal: make disagreements persistent, stateful and queryable.

Build `lifecycle.py`:
- `create_disagreement(pair_verdict)`: idempotent on (candidate_slug, competency, interviewer_a_id, interviewer_b_id, kind), so several fact pairs between the same two interviewers on one competency produce one disagreement (use the highest-severity pair, ties by most recent round); state RAISED; writes a transition row and a Hindsight retain.
- `mark_probe_asked(id)`.
- `submit_resolution(id, resolution_type, note, new_contexts=None)`: implements the mapping in `AGENTS.md` and retains the note to Hindsight as a fact linked to the disagreement_id. BOTH_HOLD_UNDER_DIFFERENT_CONTEXT requires both new contexts and retro-tags the facts (keeping `task_context_history`). UI copy comes from a static template map and is passed through `lint_text` in a test.
- `finalize(slug)`: moves every non-RESOLVED disagreement to STILL_OPEN with a transition, and returns a final summary that lists them.
- `open_disagreements(slug)`: from SQLite, not from Hindsight.
- An invalid transition raises `InvalidTransition`.

Acceptance tests (offline): each resolution type produces the right state; an invalid transition raises; `finalize` marks unresolved ones STILL_OPEN and they appear in `open_disagreements_summary`; re-evaluating a candidate does not create duplicates; no resolution copy contains banned phrases.

STOP.

---

## PART 7 — API and React + Tailwind UI (75–90 min)

Goal: something a judge can click through.

Build FastAPI endpoints exactly as specified in Section 8 of `APPLICATION_SPEC.md`. Add CORS for the Vite dev origin. Build the UI in `frontend/` with React and Tailwind CSS: a single-page app with three tabs (Submit, Candidate, Disagreements), API base from `VITE_API_URL`, plain `fetch`. Suggested components: `SubmissionForm`, `CandidateView`, `BriefingPanel`, `CompetencyCard`, `ClaimPair`, `PathBadge`, `DisagreementsPanel`, `ProvenanceTimeline`, `ResolutionForm`. Follow the UI fairness rule in `AGENTS.md`: `ClaimPair` renders both claims identically. Screen contents, field labels, button labels and all user-facing text come from Sections 7 and 9 of `APPLICATION_SPEC.md`; use them word for word.

Acceptance: from a clean DB, submit two conflicting feedbacks in the browser and see a CONTRADICTION card with its path line, resolve it, and see the state change without a page reload issue. Screenshot or describe the flow.

STOP.

---

## PART 8 — Seed data, end-to-end run, demo notes (45 min)

Goal: a repeatable demo that shows all four verdicts and the memory arc.

Build `scripts/seed.py` (synthetic, realistic feedback text written by you, no real people):
- **Candidate A, 3 rounds, 3 interviewers.** Round 1 and round 2 disagree on `system_design` in the same context (real CONTRADICTION). `concurrency` is a COMPLEMENTARY agreement. `communication` is rated differently across a live-coding and a behavioral round (CONTEXT_SPLIT). `culture_add` has one source only (INSUFFICIENT_EVIDENCE). Round 3 ends with a resolution for the system_design disagreement.
- **Candidate B.** One competency where the second interviewer is anchored and agrees (`anchored_agreement_only`), and one where the second interviewer is anchored and disagrees (`anchored_dissent`).
- Include a short synthetic debrief transcript (about 10 lines) in which the panel discusses the system_design disagreement, and use it to write the round-3 resolution entry.
- Seed 6–8 synthetic post-hire outcome records for Part 10.
- Support two modes: pre-seed rounds 1–2 (record timestamps), and submit round 3 live.
Write `DEMO_NOTES.md`: a 3-minute demo script, a two-sentence positioning statement, exactly what is pre-seeded and when, the synthetic-data disclosure, known limitations, and a one-paragraph honest answer to each of: "isn't this an LLM wrapper?", "isn't this biased?", "how does it generalize?".

Acceptance: `python scripts/seed.py --reset` then the browser flow works end to end, and the evaluation JSON contains all four verdicts across the two candidates.

STOP.

---

## PART 9 — Baseline comparison (STRETCH, 30 min)

Goal: honest evidence that the architecture, not just prompting, does the work.

Build `baseline_comparison/` (own README, never imported by `app/`):
- Baseline 1: single prompt, "summarize this panel's feedback into a fit assessment".
- Baseline 2: same, but the prompt explicitly instructs the model not to favor any interviewer.
- Run both 5 times on the same Candidate A input and run `lint_text` on every output. Report the counts of lint violations per baseline and for Panel's own outputs, in a table in the README.

Acceptance: README table with the counts and a two-sentence honest reading.

STOP.

---

## PART 10 — Calibration (CUT FIRST, 30–45 min)

Only do this if everything above is done and tested.

Build a separate `GET /calibration` endpoint and a separate panel in the UI, never embedded inside a competency card or shown next to a live disagreement.
- Data: synthetic post-hire outcome records for candidates who were hired. Retain them to the Hindsight bank `interviewer-calibration-global`, and compute the statistics in code from SQLite.
- Logic (pure code): for each interviewer and competency with at least 3 outcome records, report how many hired candidates they rated negatively and how many of those had positive outcomes. Suppress anything below 3.
- Every line carries: sample size, "synthetic data", and "hired candidates only, rejected candidates have no outcomes". Phrasing is historical and neutral, never "this interviewer is unreliable".

Acceptance: offline tests for suppression at n < 3, disclosure text present, and no banned phrases.

STOP.

---

## PART 11 — Demo hardening (20–30 min)

Build:
- Retry with backoff (3 tries) on Groq and Hindsight calls; on final failure raise a clear error (no fabrication).
- Identical-input cache for LLM calls (hash of the prompt and schema), so a repeated demo run gives identical output.
- A `scripts/preflight.py` that checks env vars, NLI model load, Hindsight reachability and Groq reachability, to run 10 minutes before the demo.
- Record a screen capture of a full successful run as the fallback.

Acceptance: preflight prints all PASS; running the demo twice gives identical evaluation JSON.

STOP.

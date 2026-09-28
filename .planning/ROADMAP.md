# ROADMAP.md — Panel

## Milestone 1: MVP through Demo-Ready (Parts 0–8)

Priority order per BUILD_STEPS.md: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

---

## Phase 0 — Scaffold and Smoke Tests
**Status:** `not_started`
**Time estimate:** 30–45 min
**Goal:** Prove every external dependency works before building on it.

### Deliverables
- Repo layout with all canonical files (empty stubs)
- `DECISIONS.md` with verified Hindsight API signatures
- `scripts/smoke.py` passing: Hindsight retain/recall, Groq structured output, NLI label order
- `frontend/` scaffolded with Vite + React + Tailwind

### Acceptance checks
- [ ] `python scripts/smoke.py` prints PASS for all 3 checks
- [ ] `npm run build` in `frontend/` succeeds
- [ ] `DECISIONS.md` documents Hindsight signatures + Groq structured-output support

---

## Phase 1 — Data Model and Config
**Status:** `not_started`
**Time estimate:** 30 min
**Goal:** Single source of truth for enums, schema, constants.

### Deliverables
- `app/enums.py` — all enums from AGENTS.md
- `app/thresholds.py` — NLI_CONTRADICTION_HIGH, LOW, MAX_PAIRS (marked PROVISIONAL)
- `app/db.py` — all 9 SQLite tables with UNIQUE constraints
- `app/models.py` — Pydantic output contract

### Acceptance checks
- [ ] `pytest -m "not live"` passes: DB create, insert candidate+submissions+facts, read back
- [ ] UNIQUE constraint on disagreements prevents duplicates

---

## Phase 2 — Stage 1: Ingestion and Memory
**Status:** `not_started`
**Time estimate:** 60 min
**Goal:** Raw text → validated atomic facts → SQLite + Hindsight.

### Deliverables
- `app/ingest.py` — Groq fact extraction + span validation + retry
- `app/memory.py` — Hindsight wrapper (retain_fact, recall_for_candidate)
- `scripts/remirror.py` — retry mirrored=false facts
- POST /submissions validation + processing per spec

### Acceptance checks
- [ ] Offline: unit tests for span validator (1 pass, 1 fail) with mocked LLM
- [ ] Live: ingest 5-sentence feedback, show stored facts + recall query

---

## Phase 3 — Stage 2 + 2.5: Pure-Code Gates
**Status:** `not_started`
**Time estimate:** 45 min
**Goal:** Sufficiency gate + context routing, fully deterministic.

### Deliverables
- `app/gates.py` — build_pairs(), sufficiency(), route_context()

### Acceptance checks (8 test cases)
- [ ] 1. One interviewer → single_source
- [ ] 2. Two anchored + same polarity → anchored_agreement_only
- [ ] 3. One independent + one anchored + opposite → eligible, anchored_dissent=true
- [ ] 4. Two independent + same context → needs_stage3
- [ ] 5. Different context + opposite polarity → CONTEXT_SPLIT
- [ ] 6. Different context + same polarity → COMPLEMENTARY
- [ ] 7. Same interviewer + opposite polarity → self_revision note, no pair
- [ ] 8. `other` competency fact never in a pair

**CHECKPOINT A — STOP and review before Phase 4**

---

## Phase 4 — Stage 3: NLI Classification + Calibration
**Status:** `not_started`
**Time estimate:** 60–75 min
**Goal:** NLI + decision table, empirically checked thresholds.

### Deliverables
- `app/classify.py` — nli_scores(), decide_pair(), aggregate()
- `fixtures/nli_pairs.jsonl` — 24+ fixture pairs
- `scripts/calibrate_nli.py` — threshold calibration script

### Acceptance checks
- [ ] Offline: all branches of decision table covered with injected c values
- [ ] Live: calibration script prints per-label distribution + held-out accuracy

**CHECKPOINT B — show held-out results, STOP**

---

## Phase 5 — Stage 4: Synthesis, Guards, Provenance, Briefing
**Status:** `not_started`
**Time estimate:** 60 min
**Goal:** Grounded text with hard guards against adjudication.

### Deliverables
- `app/synthesis.py` — adjudicate(), follow_up(), briefing(), lint_text()
- `app/provenance.py` — static verdict_path → human text map
- evaluate_candidate() in main.py (idempotent)

### Acceptance checks
- [ ] Offline: lint_text — 8 phrases fail (including "appears more thorough", "seems more reliable"), 3 neutral pass
- [ ] Offline: provenance map covers all verdict_path values
- [ ] Live: evaluate seeded candidate, show full JSON

---

## Phase 6 — Disagreement Lifecycle and Resolution
**Status:** `not_started`
**Time estimate:** 45 min
**Goal:** Persistent, stateful, queryable disagreements.

### Deliverables
- `app/lifecycle.py` — create_disagreement(), mark_probe_asked(), submit_resolution(), finalize(), open_disagreements()
- InvalidTransition exception

### Acceptance checks
- [ ] Each resolution type → correct state
- [ ] Invalid transition raises
- [ ] finalize() marks unresolved as STILL_OPEN
- [ ] Re-evaluate does not create duplicates
- [ ] No resolution copy contains banned phrases

---

## Phase 7 — API and React/Tailwind UI
**Status:** `not_started`
**Time estimate:** 75–90 min
**Goal:** Something a judge can click through.

### Deliverables
- All 8 API endpoints in main.py (per APPLICATION_SPEC.md §8)
- CORS for Vite dev origin
- React UI: 3 tabs — Submit, Candidate, Disagreements
- Components: SubmissionForm, CandidateView, BriefingPanel, CompetencyCard, ClaimPair, PathBadge, DisagreementsPanel, ProvenanceTimeline, ResolutionForm

### Acceptance checks
- [ ] Submit two conflicting feedbacks → CONTRADICTION card with path line
- [ ] Resolve it → state changes without page reload issue
- [ ] ClaimPair renders both claims identically (UI fairness)

---

## Phase 8 — Seed Data, End-to-End Run, Demo Notes
**Status:** `not_started`
**Time estimate:** 45 min
**Goal:** Repeatable demo with all four verdicts.

### Deliverables
- `scripts/seed.py` — Candidate A (all 4 verdicts) + Candidate B (anchored cases)
- `DEMO_NOTES.md` — 3-min demo script + disclosures + honest Q&A

### Acceptance checks
- [ ] `python scripts/seed.py --reset` then browser end-to-end works
- [ ] Evaluation JSON contains all four verdicts across two candidates

---

## Milestone 2: Hardening (Part 11)

## Phase 9 — Demo Hardening
**Status:** `not_started`
**Time estimate:** 20–30 min

### Deliverables
- Retry with backoff on Groq + Hindsight (3 tries)
- Identical-input LLM cache (hash of prompt + schema)
- `scripts/preflight.py` — env vars, NLI, Hindsight, Groq checks

### Acceptance checks
- [ ] Preflight prints all PASS
- [ ] Running demo twice gives identical evaluation JSON

---

## Milestone 3: Stretch (Parts 9, 10) — Cut if short on time

## Phase 10 — Baseline Comparison (STRETCH)
**Status:** `not_started`
**Time estimate:** 30 min

## Phase 11 — Calibration (CUT FIRST)
**Status:** `not_started`
**Time estimate:** 30–45 min

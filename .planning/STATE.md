# STATE.md â€” Panel Project State

## Current state
- **Active milestone:** Milestone 1 â€” MVP through Demo-Ready
- **Current phase:** Phase 0 â€” Scaffold and Smoke Tests (not started)
- **Next action:** Run `/gsd-plan-phase 0` to plan Phase 0, then `/gsd-execute-phase 0`

## What exists in the workspace right now
- `AGENTS.md` âœ… (rules file)
- `APPLICATION_SPEC.md` âœ… (full spec v5)
- `BUILD_STEPS.md` âœ… (phase-by-phase instructions Parts 0â€“11)
- `.planning/PROJECT.md` âœ…
- `.planning/REQUIREMENTS.md` âœ…
- `.planning/ROADMAP.md` âœ…
- `.planning/STATE.md` âœ… (this file)
- `.planning/config.json` âœ…

## What does NOT exist yet
- `app/` directory and all backend files
- `tests/` directory
- `scripts/` directory
- `frontend/` directory
- `DECISIONS.md`
- `DEMO_NOTES.md`
- Any code

## Key decisions already locked (from spec)
- Backend: FastAPI + SQLite + Pydantic
- LLM: `openai/gpt-oss-120b` (fallback `qwen/qwen3-32b`, record in DECISIONS.md)
- NLI: `cross-encoder/nli-deberta-v3-xsmall`
- Memory: hindsight-client
- Frontend: Vite + React + Tailwind CSS
- DB: 9 tables exactly as in APPLICATION_SPEC.md Â§5
- No auth, no scoring, no hire/no-hire recommendation

## Open questions (to resolve in DECISIONS.md after smoke tests)
- Exact Hindsight API signatures (retain, recall, reflect)
- Whether Groq `openai/gpt-oss-120b` supports JSON schema structured output
- Which LLM Hindsight `reflect` uses internally

## Checkpoints
- CHECKPOINT A after Phase 3 (gates tests must pass before Phase 4)
- CHECKPOINT B after Phase 4 (NLI calibration results review)

## Phase completion log
| Phase | Status | Completed At |
|---|---|---|
| Phase 0 â€” Scaffold + Smoke | not_started | â€” |
| Phase 1 â€” Data Model | not_started | â€” |
| Phase 2 â€” Ingestion + Memory | not_started | â€” |
| Phase 3 â€” Gates (CHECKPOINT A) | not_started | â€” |
| Phase 4 â€” NLI Classification (CHECKPOINT B) | not_started | â€” |
| Phase 5 â€” Synthesis + Guards | not_started | â€” |
| Phase 6 â€” Lifecycle | not_started | â€” |
| Phase 7 â€” API + UI | not_started | â€” |
| Phase 8 â€” Seed Data + Demo | not_started | â€” |
| Phase 9 â€” Hardening | not_started | â€” |
| Phase 10 â€” Baseline Comparison (STRETCH) | not_started | â€” |
| Phase 11 â€” Calibration (CUT FIRST) | not_started | â€” |

## Phase plan index (all written)

| Phase | PLAN.md | Status |
|---|---|---|
| 0 — Scaffold + Smoke | phase-0/PLAN.md | planned |
| 1 — Data Model | phase-1/PLAN.md | planned |
| 2 — Ingestion | phase-2/PLAN.md | planned |
| 3 — Gates | phase-3/PLAN.md | planned |
| 4 — NLI | phase-4/PLAN.md | planned |
| 5 — Synthesis | phase-5/PLAN.md | planned |
| 6 — Lifecycle | phase-6/PLAN.md | planned |
| 7 — API + UI | phase-7/PLAN.md | planned |
| 8 — Seed + Demo | phase-8/PLAN.md | planned |
| 9 — Hardening | phase-9/PLAN.md | planned |
| 10 — Baselines | phase-10/PLAN.md | stretch |
| 11 — Calibration | phase-11/PLAN.md | cut-first |

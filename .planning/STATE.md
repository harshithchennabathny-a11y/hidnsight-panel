# STATE.md — Panel Project State

## Current state
- **Active milestone:** Milestone 1 — MVP through Demo-Ready
- **Current phase:** Phase 0 — Scaffold and Smoke Tests (not started)
- **Next action:** Run `/gsd-plan-phase 0` to plan Phase 0, then `/gsd-execute-phase 0`

## What exists in the workspace right now
- `AGENTS.md` ✅ (rules file)
- `APPLICATION_SPEC.md` ✅ (full spec v5)
- `BUILD_STEPS.md` ✅ (phase-by-phase instructions Parts 0–11)
- `.planning/PROJECT.md` ✅
- `.planning/REQUIREMENTS.md` ✅
- `.planning/ROADMAP.md` ✅
- `.planning/STATE.md` ✅ (this file)
- `.planning/config.json` ✅

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
- DB: 9 tables exactly as in APPLICATION_SPEC.md §5
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
| Phase 0 — Scaffold + Smoke | not_started | — |
| Phase 1 — Data Model | not_started | — |
| Phase 2 — Ingestion + Memory | not_started | — |
| Phase 3 — Gates (CHECKPOINT A) | not_started | — |
| Phase 4 — NLI Classification (CHECKPOINT B) | not_started | — |
| Phase 5 — Synthesis + Guards | not_started | — |
| Phase 6 — Lifecycle | not_started | — |
| Phase 7 — API + UI | not_started | — |
| Phase 8 — Seed Data + Demo | not_started | — |
| Phase 9 — Hardening | not_started | — |
| Phase 10 — Baseline Comparison (STRETCH) | not_started | — |
| Phase 11 — Calibration (CUT FIRST) | not_started | — |

# STATE.md — Panel Project State

## Current state
- **Active milestone:** Milestone 1 — MVP through Demo-Ready ✅ COMPLETE
- **Current phase:** All phases complete — project is demo-ready and submitted
- **Next action:** None. Project submitted for hackathon on 29 September 2026.

## What exists in the workspace right now
- `AGENTS.md` ✅
- `APPLICATION_SPEC.md` ✅
- `BUILD_STEPS.md` ✅
- `DECISIONS.md` ✅
- `DEMO_NOTES.md` ✅
- `article.md` ✅ (hackathon article ready to publish)
- `.planning/PROJECT.md` ✅
- `.planning/REQUIREMENTS.md` ✅
- `.planning/ROADMAP.md` ✅
- `.planning/STATE.md` ✅ (this file)
- `.planning/config.json` ✅
- `app/` ✅ — all backend files: `enums.py, thresholds.py, db.py, models.py, memory.py, ingest.py, gates.py, classify.py, synthesis.py, provenance.py, lifecycle.py, calibration.py, config.py, main.py`
- `tests/` ✅ — `test_data_model.py, test_gates.py, test_ingest.py`
- `scripts/` ✅ — `seed.py, remirror.py, preflight.py, test_server_e2e_cycle.py`
- `frontend/` ✅ — Vite + React + Tailwind, full UI with all components
- `baseline_comparison/README.md` ✅

## Key decisions locked (from DECISIONS.md)
- Backend: FastAPI + SQLite + Pydantic
- LLM: `openai/gpt-oss-120b` (switched to `qwen/qwen3-32b` — recorded in DECISIONS.md)
- NLI: `cross-encoder/nli-deberta-v3-xsmall` (with keyword fallback)
- Memory: hindsight-client
- Frontend: Vite + React + Tailwind CSS
- DB: 9 tables as in APPLICATION_SPEC.md §5
- No auth, no scoring, no hire/no-hire recommendation (R10)

## Phase completion log
| Phase | Status | Completed At |
|---|---|---|
| Phase 0 — Scaffold + Smoke | ✅ complete | 29-Sep-2026 |
| Phase 1 — Data Model | ✅ complete | 29-Sep-2026 |
| Phase 2 — Ingestion + Memory | ✅ complete | 29-Sep-2026 |
| Phase 3 — Gates (CHECKPOINT A) | ✅ complete | 29-Sep-2026 |
| Phase 4 — NLI Classification (CHECKPOINT B) | ✅ complete | 29-Sep-2026 |
| Phase 5 — Synthesis + Guards | ✅ complete | 29-Sep-2026 |
| Phase 6 — Lifecycle | ✅ complete | 29-Sep-2026 |
| Phase 7 — API + UI | ✅ complete | 29-Sep-2026 |
| Phase 8 — Seed Data + Demo | ✅ complete | 29-Sep-2026 |
| Phase 9 — Hardening | ✅ complete | 29-Sep-2026 |
| Phase 10 — Baseline Comparison (STRETCH) | ✅ complete | 29-Sep-2026 |
| Phase 11 — Calibration (CUT FIRST) | ✅ complete | 29-Sep-2026 |

## Phase plan index
| Phase | PLAN.md | Status |
|---|---|---|
| 0 — Scaffold + Smoke | phase-0/PLAN.md | ✅ done |
| 1 — Data Model | phase-1/PLAN.md | ✅ done |
| 2 — Ingestion | phase-2/PLAN.md | ✅ done |
| 3 — Gates | phase-3/PLAN.md | ✅ done |
| 4 — NLI | phase-4/PLAN.md | ✅ done |
| 5 — Synthesis | phase-5/PLAN.md | ✅ done |
| 6 — Lifecycle | phase-6/PLAN.md | ✅ done |
| 7 — API + UI | phase-7/PLAN.md | ✅ done |
| 8 — Seed + Demo | phase-8/PLAN.md | ✅ done |
| 9 — Hardening | phase-9/PLAN.md | ✅ done |
| 10 — Baselines | phase-10/PLAN.md | ✅ done |
| 11 — Calibration | phase-11/PLAN.md | ✅ done |

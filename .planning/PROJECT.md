# PROJECT.md — Panel

## What this project is

**Panel** is a hiring-panel web application (FastAPI backend + React/Tailwind frontend) that tracks disagreements between interviewers as persistent, stateful objects — not averages.

When two interviewers disagree on the same competency, Panel creates a **disagreement** with a lifecycle (`RAISED → PROBE_ASKED → RESOLVED / ESCALATED → STILL_OPEN`), a suggested follow-up probe, and a full audit trail. It does not score, rank, or recommend a hire decision.

## The core loop (6 steps)

1. Interviewer submits free-text feedback → system extracts atomic facts (LLM, Groq)
2. Facts stored in SQLite + mirrored to Hindsight memory (`hiring-candidate-{slug}`)
3. Per competency: sufficiency gate → context routing → NLI classification → LLM adjudication (only if escalated)
4. CONTRADICTION or CONTEXT_SPLIT → creates a `disagreement` row with lifecycle
5. Coordinator records resolution outcome → state machine advances
6. Briefing built from Hindsight memory for next interviewer before each round

## Key design constraints

- **SQLite is the source of truth.** Hindsight mirrors; never enumerate from Hindsight.
- **Gates are pure functions.** No network calls in sufficiency, context routing, or decision table.
- **Verdicts are historical.** Never recomputed after resolution.
- **No adjudication.** No text anywhere may imply one interviewer is more credible.
- **Synthetic data only.** No real candidate data ever.
- **No auth, no scoring, no hire/no-hire recommendation.**

## Tech stack

| Layer | Choice |
|---|---|
| Backend | FastAPI + SQLite (sqlite3) + Pydantic |
| LLM | Groq (`openai/gpt-oss-120b`, fallback `qwen/qwen3-32b`) |
| NLI | `cross-encoder/nli-deberta-v3-xsmall` via sentence-transformers |
| Memory | hindsight-client |
| Frontend | Vite + React + Tailwind CSS |
| Tests | pytest (offline: `pytest -m "not live"`) |

## Canonical file map

```
app/
  enums.py          — all enums
  thresholds.py     — NLI_CONTRADICTION_HIGH, LOW, MAX_PAIRS
  db.py             — SQLite schema
  models.py         — Pydantic output contract
  memory.py         — Hindsight wrapper
  ingest.py         — Stage 1: LLM fact extraction + span validation
  gates.py          — Stage 2 + 2.5: pure-code gates
  classify.py       — Stage 3: NLI + decision table
  synthesis.py      — Stage 4: LLM adjudication + lint guard + briefing
  provenance.py     — Static verdict_path → human text map
  lifecycle.py      — Disagreement state machine
  main.py           — FastAPI app + all endpoints
tests/
scripts/
  smoke.py          — dep verification
  seed.py           — demo seed data
  remirror.py       — retry unmirrored facts
  calibrate_nli.py  — NLI threshold calibration
  preflight.py      — pre-demo health check
baseline_comparison/
frontend/
DECISIONS.md
DEMO_NOTES.md
AGENTS.md
APPLICATION_SPEC.md
BUILD_STEPS.md
```

## Authoritative references

- `AGENTS.md` — rules (wins on any conflict)
- `APPLICATION_SPEC.md` — full spec (data model, screens, API, exact text, worked example)
- `BUILD_STEPS.md` — phase-by-phase build instructions (Parts 0–11)

## Success criteria

- `pytest -m "not live"` passes
- All four verdicts appear in seeded data
- No text implies which interviewer is right
- `DEMO_NOTES.md` discloses exactly what is synthetic

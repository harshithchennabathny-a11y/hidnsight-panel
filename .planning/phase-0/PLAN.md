---
phase: 0
title: Scaffold and Smoke Tests
status: not_started
wave_count: 2
estimated_minutes: 40
---

# Phase 0 Plan — Scaffold and Smoke Tests

## Goal
Prove every external dependency works (Hindsight, Groq, NLI model) and create the complete repo skeleton before writing a single line of application logic.

## Pre-conditions
- Python 3.10+ available
- Node 18+ available
- `GROQ_API_KEY` set in environment
- `hindsight-client` installed in Python env
- `sentence-transformers` installed

## Risk flags
- ⚠️ **Hindsight API is unknown** — must read from installed package, not guessed
- ⚠️ **Groq model `openai/gpt-oss-120b`** may not support JSON-schema structured output; must test and fall back
- ⚠️ **NLI label order** must be read from model config, not assumed

---

## Wave 1 — Repo skeleton (no deps needed)

### Task 0.1 — Create all directory stubs
Create these directories and empty `__init__.py` or stub files:
```
app/__init__.py
tests/__init__.py
scripts/.gitkeep
baseline_comparison/.gitkeep
fixtures/.gitkeep
frontend/  (created by Vite in Task 0.4)
```

Create stub files (just a module docstring, no logic):
- `app/enums.py`
- `app/thresholds.py`
- `app/db.py`
- `app/models.py`
- `app/memory.py`
- `app/ingest.py`
- `app/gates.py`
- `app/classify.py`
- `app/synthesis.py`
- `app/provenance.py`
- `app/lifecycle.py`
- `app/main.py`

Create root files:
- `DECISIONS.md` (stub — to be filled by smoke.py findings)
- `DEMO_NOTES.md` (stub)
- `.env.example` (see below)
- `requirements.txt`
- `pytest.ini`

**`.env.example` content:**
```
# Groq
GROQ_API_KEY=your_groq_key_here

# Hindsight — fill after reading installed package
HINDSIGHT_API_KEY=
HINDSIGHT_BASE_URL=
# Add any other vars the hindsight-client actually requires
```

**`pytest.ini` content:**
```ini
[pytest]
markers =
    live: marks tests as requiring live external services (Hindsight, Groq, NLI)
```

**`requirements.txt` content:**
```
fastapi
uvicorn[standard]
pydantic>=2.0
groq
hindsight-client
sentence-transformers
torch
pytest
pytest-asyncio
httpx
python-dotenv
```

### Task 0.2 — Read hindsight-client installed package
Run: `python -c "import hindsight; help(hindsight)"` and also inspect:
- `pip show hindsight-client` for version and location
- Read the source or installed docs to find:
  - How to instantiate the client
  - `retain(content, bank, metadata, tags)` exact signature
  - `recall(query, bank, ...)` exact signature  
  - `reflect(query, bank, ...)` exact signature (note which LLM it uses internally)
  - How banks are created (auto on first retain, or explicit?)
  - Metadata field names and tag format

Write all findings into `DECISIONS.md` under section `## Hindsight API (verified from installed package)`.

---

## Wave 2 — Smoke tests (requires live credentials)

### Task 0.3 — Write `scripts/smoke.py`

Three independent checks, each prints `PASS` or `FAIL: <reason>`.

**Check A — Hindsight retain + recall:**
```python
# Use a scratch bank, never the real hiring bank
bank = "smoke-test-scratch"
# retain one fact with metadata
# recall it back with a matching query
# assert the content comes back
# print PASS or FAIL
```

**Check B — Groq structured output:**
```python
# Try JSON-schema structured output first
# Schema: {"type": "object", "properties": {"verdict": {"enum": ["A","B","C"]}}, "required": ["verdict"]}
# If it succeeds: print PASS, note "structured output supported"
# If it fails (feature not available): fall back to JSON mode + pydantic parse + one retry
# Print which mode worked
# Write result to DECISIONS.md: "Groq structured output: supported/not-supported (fallback: JSON mode + pydantic)"
```

**Check C — NLI model label order:**
```python
from sentence_transformers import CrossEncoder
model = CrossEncoder("cross-encoder/nli-deberta-v3-xsmall")
# Print model.config.id2label
# Assert index 0 == "contradiction", index 1 == "entailment", index 2 == "neutral"
# Classify one obviously contradicting pair:
#   A: "The candidate demonstrated excellent system design skills."
#   B: "The candidate showed poor system design ability."
# Print raw scores and label mapping
# Print PASS if label order matches expected
```

### Task 0.4 — Scaffold frontend with Vite + React + Tailwind

```bash
# In workspace root:
npm create vite@latest frontend -- --template react
cd frontend
npm install
# Add Tailwind — check https://tailwindcss.com/docs/installation/using-vite for current steps
npm install -D tailwindcss @tailwindcss/vite
# Follow the current docs to configure vite.config.js and add @import "tailwindcss" to index.css
# Create .env.local with VITE_API_URL=http://localhost:8000
npm run build  # must succeed
```

Also add to `app/main.py` stub:
```python
from fastapi.middleware.cors import CORSMiddleware
# app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], ...)
```

### Task 0.5 — Update DECISIONS.md with all findings

After smoke.py runs, fill in DECISIONS.md:

```markdown
## Hindsight API (verified from installed package vX.Y.Z)
- Client instantiation: ...
- retain signature: ...
- recall signature: ...
- reflect signature: ... (uses LLM: ...)
- Bank creation: auto / explicit
- Metadata fields: ...
- Tag format: ...

## Groq Structured Output
- Model: openai/gpt-oss-120b
- Structured output supported: yes/no
- Fallback used: JSON mode + pydantic validation + 1 retry (if no)
- Model switched to: qwen/qwen3-32b (if primary fails, record here)

## NLI Label Order (cross-encoder/nli-deberta-v3-xsmall)
- id2label: {0: "contradiction", 1: "entailment", 2: "neutral"}
- Asserted from model config, not hardcoded
```

---

## Acceptance Verification

| Check | Command | Expected |
|---|---|---|
| Smoke tests | `python scripts/smoke.py` | All 3 print PASS |
| Frontend build | `cd frontend && npm run build` | Exit 0, dist/ created |
| DECISIONS.md | Manual review | Hindsight sigs + Groq support documented |
| File layout | `find app/ -name "*.py"` | All 12 files exist |

## Outputs → next phase consumes
- Verified Hindsight client usage pattern (for `memory.py`)
- Verified Groq structured-output mode (for `ingest.py`, `synthesis.py`)
- Confirmed NLI label order (for `classify.py` assertion test)
- `frontend/` scaffolded (for Phase 7)
- `DECISIONS.md` initialized (updated every phase)

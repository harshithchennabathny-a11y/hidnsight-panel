---
phase: 9
title: Demo Hardening
status: not_started
wave_count: 1
estimated_minutes: 25
depends_on: [phase-8]
---

# Phase 9 Plan — Demo Hardening

## Goal
Retry/backoff on external calls, identical-input LLM caching, and a preflight script that verifies all deps before a demo. Running the demo twice gives identical JSON.

## Pre-conditions
- Phase 8 complete (seed data working, browser flow verified)

---

## Wave 1 — Three hardening tasks

### Task 9.1 — Retry with exponential backoff

Add a shared utility in `app/utils.py`:

```python
# app/utils.py
import time, functools, logging

logger = logging.getLogger(__name__)

def with_retry(max_attempts: int = 3, base_delay: float = 1.0, exceptions=(Exception,)):
    """Decorator: retry with exponential backoff on specified exceptions."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        logger.error(f"{fn.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(f"{fn.__name__} attempt {attempt} failed: {e}. Retrying in {delay:.1f}s...")
                    time.sleep(delay)
        return wrapper
    return decorator
```

Apply to:
- `memory.retain_fact` — wrap the Hindsight client call
- `memory.retain_transition` — same
- `memory.retain_resolution` — same
- `memory.recall_for_candidate` — same
- `ingest._extract_facts_llm` — wrap the Groq call
- `synthesis._groq_call` — wrap all Groq calls

```python
# In memory.py — example
from app.utils import with_retry

@with_retry(max_attempts=3, base_delay=1.0)
def retain_fact(fact: dict, candidate_slug: str) -> None:
    ...

# In synthesis.py
@with_retry(max_attempts=3, base_delay=1.0)
def _groq_call(system: str, user: str, json_mode: bool = True) -> str:
    ...
```

After 3 failures the original exception propagates — caller handles it (502 in API layer). No fabrication.

### Task 9.2 — Identical-input LLM cache

Add to `app/utils.py`:

```python
import hashlib, json, os
from pathlib import Path

_CACHE_DIR = Path(os.getenv("LLM_CACHE_DIR", ".llm_cache"))

def _cache_key(system: str, user: str, schema: dict | None) -> str:
    payload = json.dumps({"system": system, "user": user, "schema": schema}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()

def cache_get(system: str, user: str, schema: dict | None = None) -> str | None:
    key = _cache_key(system, user, schema)
    path = _CACHE_DIR / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())["response"]
    return None

def cache_set(system: str, user: str, schema: dict | None, response: str) -> None:
    _CACHE_DIR.mkdir(exist_ok=True)
    key = _cache_key(system, user, schema)
    path = _CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps({"response": response}))
```

Integrate into `synthesis._groq_call`:

```python
def _groq_call(system: str, user: str, json_mode: bool = True, schema=None) -> str:
    # Check cache first
    cached = cache_get(system, user, schema)
    if cached:
        return cached

    # Make actual call (with retry decorator)
    response = _groq_call_live(system, user, json_mode, schema)

    # Store in cache
    cache_set(system, user, schema, response)
    return response
```

Add `.llm_cache/` to `.gitignore`. Repeat-demo runs hit cache, give identical output.

### Task 9.3 — `scripts/preflight.py`

Checks all dependencies 10 minutes before the demo. Each check prints `[PASS]` or `[FAIL] <reason>`.

```python
#!/usr/bin/env python
"""
preflight.py — run 10 minutes before the demo.
Checks: env vars, NLI model, Hindsight, Groq.
"""
import sys, os
sys.path.insert(0, ".")

PASS = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"

def check(name, fn):
    try:
        fn()
        print(f"{PASS} {name}")
        return True
    except Exception as e:
        print(f"{FAIL} {name}: {e}")
        return False

def check_env_vars():
    required = ["GROQ_API_KEY"]
    # Add Hindsight vars from DECISIONS.md
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing env vars: {missing}")

def check_nli_model():
    from sentence_transformers import CrossEncoder
    model = CrossEncoder("cross-encoder/nli-deberta-v3-xsmall")
    labels = model.config.id2label
    assert labels[0] == "contradiction", f"Unexpected label order: {labels}"
    # Quick smoke score
    scores = model.predict([("A is positive.", "A is negative.")], apply_softmax=True)
    assert scores[0][0] > 0.5, f"Expected contradiction score > 0.5, got {scores[0][0]}"

def check_hindsight():
    from app.memory import _client, bank_name
    client = _client()
    # Retain and recall a test item
    client.retain("preflight-test", bank="preflight-scratch", metadata={}, tags=["type:test"])
    results = client.recall("preflight-test", bank="preflight-scratch", limit=1)
    assert results, "Hindsight recall returned empty"

def check_groq():
    from groq import Groq
    client = Groq()
    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": "Reply with the word READY only."}],
        max_tokens=5,
    )
    content = resp.choices[0].message.content.strip()
    assert "READY" in content.upper(), f"Unexpected response: {content}"

def check_db():
    from app.db import get_connection
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    assert count > 0, "No candidates in DB — run seed.py first"
    print(f"         ({count} candidates seeded)")

def check_server():
    import requests
    r = requests.get("http://localhost:8000/candidates", timeout=3)
    assert r.status_code == 200, f"Server returned {r.status_code}"

if __name__ == "__main__":
    checks = [
        ("Environment variables",      check_env_vars),
        ("NLI model loads + scores",   check_nli_model),
        ("Hindsight reachable",        check_hindsight),
        ("Groq API reachable",         check_groq),
        ("SQLite DB + seed data",      check_db),
        ("FastAPI server running",     check_server),
    ]

    results = [check(name, fn) for name, fn in checks]
    print()
    if all(results):
        print("✓ All checks passed. Ready for demo.")
    else:
        failed = sum(1 for r in results if not r)
        print(f"✗ {failed} check(s) failed. Fix before demo.")
        sys.exit(1)
```

---

## Acceptance Verification

| Check | Command | Expected |
|---|---|---|
| Preflight all PASS | `python scripts/preflight.py` | All 6 checks green |
| Cache works | Run eval twice, compare JSON | Identical output |
| Retry logs visible | Temporarily break Groq key, watch logs | 3 attempts then clear error |
| No fabrication on failure | Let all retries fail | 502 with clear message, never a made-up result |

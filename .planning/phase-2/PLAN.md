---
phase: 2
title: Stage 1 — Ingestion and Memory
status: not_started
wave_count: 2
estimated_minutes: 60
depends_on: [phase-0, phase-1]
---

# Phase 2 Plan — Ingestion and Memory

## Goal
`POST /submissions` → LLM extracts atomic facts → span-validated → SQLite stored → Hindsight mirrored.

## Pre-conditions
- Phase 0: DECISIONS.md has Groq structured-output mode, Hindsight signatures
- Phase 1: `enums.py`, `db.py`, `models.py` complete

---

## Wave 1 — Core logic (ingest.py + memory.py)

### Task 2.1 — `app/memory.py`

Thin wrapper using the **exact Hindsight signatures from DECISIONS.md**.

```python
# memory.py
import os
from hindsight import <ClientClass>   # use real import from DECISIONS.md

def _client():
    # Initialize using env vars documented in DECISIONS.md
    return <ClientClass>(...)

def bank_name(candidate_slug: str) -> str:
    return f"hiring-candidate-{candidate_slug}"

def retain_fact(fact: dict, candidate_slug: str) -> None:
    """Retain a fact to the candidate's Hindsight bank. Raises on failure."""
    client = _client()
    client.retain(
        content=fact["claim_normalized"],
        bank=bank_name(candidate_slug),
        metadata={
            "candidate": candidate_slug,
            "interviewer": fact["interviewer_id"],
            "round": fact["round"],
            "competency": fact["competency"],
            "fact_id": fact["fact_id"],
        },
        tags=["type:fact"],
    )

def retain_transition(disagreement_id: str, state: str, note: str, candidate_slug: str) -> None:
    """Retain a lifecycle transition."""
    client = _client()
    client.retain(
        content=f"Disagreement {disagreement_id} moved to {state}. {note or ''}".strip(),
        bank=bank_name(candidate_slug),
        metadata={"disagreement_id": disagreement_id, "state": state},
        tags=["type:transition"],
    )

def retain_resolution(disagreement_id: str, note: str, candidate_slug: str) -> None:
    """Retain a resolution note."""
    client = _client()
    client.retain(
        content=note,
        bank=bank_name(candidate_slug),
        metadata={"disagreement_id": disagreement_id},
        tags=["type:resolution"],
    )

def recall_for_candidate(candidate_slug: str, query: str, limit: int = 20) -> list[str]:
    """Recall relevant facts for a candidate via semantic search."""
    client = _client()
    results = client.recall(query=query, bank=bank_name(candidate_slug), limit=limit)
    return results  # shape depends on DECISIONS.md — adapt
```

### Task 2.2 — `app/ingest.py`

```python
# ingest.py
import json, uuid
from groq import Groq   # or openai client depending on DECISIONS.md
from app.enums import Competency, Polarity

GROQ_MODEL = "openai/gpt-oss-120b"  # per AGENTS.md R11

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_normalized": {"type": "string"},
                    "competency": {"type": "string", "enum": [c.value for c in Competency]},
                    "polarity": {"type": "string", "enum": ["positive","negative","mixed","neutral"]},
                    "evidence_span": {"type": "string"}
                },
                "required": ["claim_normalized","competency","polarity","evidence_span"]
            }
        }
    },
    "required": ["facts"]
}

SYSTEM_PROMPT = """You extract atomic hiring-interview facts from interviewer feedback.

Rules:
- One claim per fact. Each claim must be self-contained: name the candidate and the competency.
- evidence_span must be a verbatim substring of the raw text — copy the exact words, do not paraphrase.
- competency must be one of the allowed values; use "other" if none fits.
- Do not infer anything not stated in the text.
- Do not add your own opinions or interpretations."""

def _extract_facts_llm(candidate_name: str, raw_text: str) -> list[dict]:
    """Call Groq and return raw list of fact dicts."""
    client = Groq()
    user_prompt = f"Candidate name: {candidate_name}\n\nFeedback:\n{raw_text}"

    # Use structured output if supported (per DECISIONS.md), else JSON mode
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        # Structured output or response_format={"type": "json_object"} — per DECISIONS.md
    )
    content = response.choices[0].message.content
    data = json.loads(content)
    return data["facts"]


def _validate_spans(facts: list[dict], raw_text: str) -> list[dict]:
    """Return list of facts with invalid spans (evidence_span not in raw_text)."""
    return [f for f in facts if f["evidence_span"] not in raw_text]


def extract_and_validate(candidate_name: str, raw_text: str) -> list[dict]:
    """
    Extract facts from raw_text. Validate evidence_spans.
    Retry once on failure. Raise ValueError if still failing after retry.
    """
    facts = _extract_facts_llm(candidate_name, raw_text)
    bad = _validate_spans(facts, raw_text)

    if bad:
        # Retry with failures quoted back
        retry_note = "The following evidence_spans were NOT verbatim substrings of the text:\n"
        for f in bad:
            retry_note += f"  - '{f['evidence_span']}'\nPlease fix these to be exact substrings.\n"
        facts = _extract_facts_llm(candidate_name, raw_text + "\n\n[CORRECTION NEEDED]\n" + retry_note)
        bad = _validate_spans(facts, raw_text)
        if bad:
            raise ValueError(
                f"evidence_span validation failed after retry. Bad spans: {[f['evidence_span'] for f in bad]}"
            )

    return facts


def build_fact_rows(facts: list[dict], submission_id: str, candidate_slug: str,
                    interviewer_id: str, round_: int, task_context: str,
                    reviewed_others_notes: bool) -> list[dict]:
    """Convert extracted facts into DB row dicts."""
    now = datetime.utcnow().isoformat() + "Z"
    rows = []
    for f in facts:
        rows.append({
            "fact_id": str(uuid.uuid4()),
            "submission_id": submission_id,
            "candidate_slug": candidate_slug,
            "interviewer_id": interviewer_id,
            "round": round_,
            "claim_normalized": f["claim_normalized"],
            "evidence_span": f["evidence_span"],
            "competency": f["competency"],
            "polarity": f["polarity"],
            "task_context": task_context,
            "task_context_history": "[]",
            "reviewed_others_notes": int(reviewed_others_notes),
            "mirrored": 0,
            "created_at": now,
        })
    return rows
```

### Task 2.3 — `scripts/remirror.py`

```python
# remirror.py — retry Hindsight mirror for facts where mirrored=0
import sys
sys.path.insert(0, ".")
from app.db import get_connection, create_tables
from app.memory import retain_fact

def remirror():
    conn = get_connection()
    facts = conn.execute("SELECT * FROM facts WHERE mirrored=0").fetchall()
    print(f"Found {len(facts)} unmirrored facts")
    success = 0
    for row in facts:
        try:
            retain_fact(dict(row), row["candidate_slug"])
            conn.execute("UPDATE facts SET mirrored=1 WHERE fact_id=?", (row["fact_id"],))
            conn.commit()
            success += 1
        except Exception as e:
            print(f"  FAIL {row['fact_id']}: {e}")
    print(f"Mirrored {success}/{len(facts)}")

if __name__ == "__main__":
    remirror()
```

---

## Wave 2 — POST /submissions endpoint (partial main.py)

### Task 2.4 — Wire POST /submissions in `app/main.py`

Processing order (per APPLICATION_SPEC.md §6.1):
1. Validate request fields (slug regex, round range, text length, enum values)
2. Check candidate not finalized → 409
3. Check no duplicate (slug, interviewer_id, round) → 409
4. Create candidate row if slug is new
5. Call `extract_and_validate()` → on ValueError raise 502
6. Insert submission + fact rows in one transaction
7. Mirror each fact to Hindsight; on failure → 502, keep SQLite data, leave mirrored=0
8. Call `evaluate_competencies(slug, touched_competencies)` (stub for now, real in Phase 3–5)
9. Return `{submission_id, facts: [FactOut], evaluation: [CompetencyAnalysis]}`

```python
import re
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

@app.post("/submissions")
def post_submission(req: SubmissionRequest):
    # 1. Validate
    if not SLUG_RE.match(req.candidate_slug):
        raise HTTPException(400, "candidate_slug must match ^[a-z0-9]+(-[a-z0-9]+)*$")
    if not 1 <= req.round <= 10:
        raise HTTPException(400, "round must be 1–10")
    if req.task_context not in TaskContext.__members__:
        raise HTTPException(400, f"task_context must be one of {list(TaskContext)}")
    if not 20 <= len(req.feedback_text) <= 4000:
        raise HTTPException(400, "feedback_text must be 20–4000 characters")

    conn = get_connection()

    # 2. Finalized check
    candidate = conn.execute("SELECT status FROM candidates WHERE slug=?", (req.candidate_slug,)).fetchone()
    if candidate and candidate["status"] == "finalized":
        raise HTTPException(409, "Candidate is finalized; no more submissions accepted")

    # 3. Duplicate check
    dup = conn.execute("SELECT 1 FROM submissions WHERE candidate_slug=? AND interviewer_id=? AND round=?",
        (req.candidate_slug, req.interviewer_id, req.round)).fetchone()
    if dup:
        raise HTTPException(409, f"Submission already exists for interviewer {req.interviewer_id} round {req.round}")

    # 4–9: create candidate, extract, store, mirror, evaluate
    ...
```

---

## Tests for Phase 2

File: `tests/test_ingest.py`

```python
import pytest
from unittest.mock import patch, MagicMock
from app.ingest import extract_and_validate, _validate_spans

RAW_TEXT = "The candidate showed excellent system design skills and poor communication ability."

def test_span_validator_pass():
    facts = [{"evidence_span": "excellent system design skills", "claim_normalized": "...", "competency": "system_design", "polarity": "positive"}]
    bad = _validate_spans(facts, RAW_TEXT)
    assert bad == []

def test_span_validator_fail():
    facts = [{"evidence_span": "great at coding", "claim_normalized": "...", "competency": "system_design", "polarity": "positive"}]
    bad = _validate_spans(facts, RAW_TEXT)
    assert len(bad) == 1

@patch("app.ingest._extract_facts_llm")
def test_extract_retries_on_bad_span(mock_llm):
    bad_fact = {"evidence_span": "DOES NOT EXIST IN TEXT", "claim_normalized": "...", "competency": "system_design", "polarity": "positive"}
    good_fact = {"evidence_span": "excellent system design skills", "claim_normalized": "...", "competency": "system_design", "polarity": "positive"}
    mock_llm.side_effect = [[bad_fact], [good_fact]]
    result = extract_and_validate("Alice", RAW_TEXT)
    assert mock_llm.call_count == 2
    assert result[0]["evidence_span"] == "excellent system design skills"

@patch("app.ingest._extract_facts_llm")
def test_extract_raises_after_two_failures(mock_llm):
    bad_fact = {"evidence_span": "NOT IN TEXT", "claim_normalized": "...", "competency": "system_design", "polarity": "positive"}
    mock_llm.return_value = [bad_fact]
    with pytest.raises(ValueError, match="validation failed after retry"):
        extract_and_validate("Alice", RAW_TEXT)
    assert mock_llm.call_count == 2
```

---

## Acceptance Verification

| Check | How |
|---|---|
| Span validator pass case | `test_span_validator_pass` |
| Span validator fail case | `test_span_validator_fail` |
| Retry on bad span | `test_extract_retries_on_bad_span` |
| 502 after 2 failures | `test_extract_raises_after_two_failures` |
| Live: ingest 5-sentence text | Manual: `curl -X POST /submissions ...` |
| Live: recall returns facts | Manual: `python -c "from app.memory import recall_for_candidate; print(...)"` |

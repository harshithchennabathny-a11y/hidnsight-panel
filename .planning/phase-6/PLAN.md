---
phase: 6
title: Disagreement Lifecycle and Resolution
status: not_started
wave_count: 2
estimated_minutes: 45
depends_on: [phase-5]
---

# Phase 6 Plan — Disagreement Lifecycle and Resolution

## Goal
Make disagreements persistent, stateful, and auditable. The state machine is the primary differentiator of Panel — every transition is logged, nothing is lost.

## Pre-conditions
- Phase 5 complete (synthesis, lint, provenance all working)
- Phase 1: db.py schema (disagreements, transitions, resolutions tables) complete

---

## Wave 1 — `app/lifecycle.py` core state machine

### Task 6.1 — `InvalidTransition` exception

```python
class InvalidTransition(Exception):
    """Raised when a state transition is not in the allowed set."""
    pass
```

### Task 6.2 — Allowed transitions table

```python
# Exact allowed transitions from AGENTS.md — do not add or remove
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "RAISED":      {"PROBE_ASKED", "RESOLVED", "ESCALATED"},
    "PROBE_ASKED": {"RESOLVED", "ESCALATED"},
    "ESCALATED":   {"PROBE_ASKED", "RESOLVED"},
    # RESOLVED and STILL_OPEN are terminal — no outgoing transitions
}

TERMINAL_STATES = {"RESOLVED", "STILL_OPEN"}

def _assert_transition(from_state: str, to_state: str):
    if from_state in TERMINAL_STATES:
        raise InvalidTransition(f"State {from_state} is terminal; no further transitions allowed.")
    allowed = ALLOWED_TRANSITIONS.get(from_state, set())
    if to_state not in allowed:
        raise InvalidTransition(
            f"Transition {from_state} → {to_state} is not allowed. "
            f"Allowed from {from_state}: {allowed}"
        )
```

### Task 6.3 — `create_disagreement(pair_verdict: dict, conn) → dict`

Idempotent on `(candidate_slug, competency, interviewer_a_id, interviewer_b_id, kind)`.

```python
def create_disagreement(pair_verdict: dict, conn) -> dict:
    """
    Create a disagreement row for a CONTRADICTION or CONTEXT_SPLIT pair.
    Idempotent: if one already exists for this (slug, comp, ivr_a, ivr_b, kind), do nothing.
    Returns the existing or newly created disagreement dict.
    """
    from app.memory import retain_transition

    slug = pair_verdict["candidate_slug"]
    comp = pair_verdict["competency"]
    kind = pair_verdict.get("kind", "CONTRADICTION")
    fact_a = pair_verdict["fact_a"]
    fact_b = pair_verdict["fact_b"]

    # Sort interviewer IDs alphabetically for the unique key
    ivr_a, ivr_b = sorted([fact_a["interviewer_id"], fact_b["interviewer_id"]])

    # Check idempotent
    existing = conn.execute(
        "SELECT * FROM disagreements WHERE candidate_slug=? AND competency=? "
        "AND interviewer_a_id=? AND interviewer_b_id=? AND kind=?",
        (slug, comp, ivr_a, ivr_b, kind)
    ).fetchone()

    if existing:
        return dict(existing)

    # Generate follow-up probe
    from app.synthesis import follow_up
    probe = follow_up(fact_a, fact_b, kind)

    now = datetime.utcnow().isoformat() + "Z"
    disagreement_id = str(uuid.uuid4())

    conn.execute(
        """INSERT INTO disagreements
           (disagreement_id, candidate_slug, competency, kind,
            interviewer_a_id, interviewer_b_id,
            fact_a_id, fact_b_id, pair_id,
            state, follow_up, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (disagreement_id, slug, comp, kind, ivr_a, ivr_b,
         fact_a["fact_id"], fact_b["fact_id"], pair_verdict["pair_id"],
         "RAISED", probe, now, now)
    )

    # First transition row (from_state=NULL)
    transition_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO transitions (transition_id, disagreement_id, from_state, to_state, note, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (transition_id, disagreement_id, None, "RAISED", "Disagreement detected", now)
    )
    conn.commit()

    # Mirror to Hindsight
    try:
        retain_transition(disagreement_id, "RAISED", "Disagreement detected", slug)
    except Exception as e:
        # Log but don't fail — SQLite is source of truth
        print(f"WARNING: Hindsight retain failed for transition {transition_id}: {e}")

    return conn.execute(
        "SELECT * FROM disagreements WHERE disagreement_id=?", (disagreement_id,)
    ).fetchone()
```

### Task 6.4 — `mark_probe_asked(disagreement_id: str, conn) → dict`

```python
def mark_probe_asked(disagreement_id: str, conn) -> dict:
    row = _get_or_404(disagreement_id, conn)
    _assert_transition(row["state"], "PROBE_ASKED")
    _write_transition(disagreement_id, row["state"], "PROBE_ASKED", "Probe marked as asked", conn)
    _update_state(disagreement_id, "PROBE_ASKED", conn)
    return _get_or_404(disagreement_id, conn)
```

### Task 6.5 — `submit_resolution(disagreement_id, resolution_type, note, context_a, context_b, conn) → dict`

Resolution mapping from AGENTS.md:
- `CONFIRMS_CLAIM_A` → RESOLVED
- `CONFIRMS_CLAIM_B` → RESOLVED
- `BOTH_HOLD_UNDER_DIFFERENT_CONTEXT` → RESOLVED + retro-tag both facts
- `NEW_INFORMATION_UNRESOLVED` → ESCALATED
- `UNCLEAR` → ESCALATED

```python
RESOLUTION_TO_STATE = {
    "CONFIRMS_CLAIM_A":                  "RESOLVED",
    "CONFIRMS_CLAIM_B":                  "RESOLVED",
    "BOTH_HOLD_UNDER_DIFFERENT_CONTEXT": "RESOLVED",
    "NEW_INFORMATION_UNRESOLVED":        "ESCALATED",
    "UNCLEAR":                           "ESCALATED",
}

def submit_resolution(
    disagreement_id: str,
    resolution_type: str,
    note: str,
    context_a: str | None,
    context_b: str | None,
    conn,
) -> dict:
    from app.memory import retain_resolution

    row = _get_or_404(disagreement_id, conn)
    to_state = RESOLUTION_TO_STATE[resolution_type]
    _assert_transition(row["state"], to_state)

    # Validate context fields
    if resolution_type == "BOTH_HOLD_UNDER_DIFFERENT_CONTEXT":
        if not context_a or not context_b:
            raise ValueError("BOTH_HOLD_UNDER_DIFFERENT_CONTEXT requires context_a and context_b")
        # Retro-tag both facts: update task_context, push old value to task_context_history
        _retag_fact(row["fact_a_id"], context_a, conn)
        _retag_fact(row["fact_b_id"], context_b, conn)
    else:
        if context_a or context_b:
            raise ValueError("context_a and context_b are only allowed for BOTH_HOLD_UNDER_DIFFERENT_CONTEXT")

    now = datetime.utcnow().isoformat() + "Z"
    resolution_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO resolutions (resolution_id, disagreement_id, resolution_type, note, context_a, context_b, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (resolution_id, disagreement_id, resolution_type, note, context_a, context_b, now)
    )

    _write_transition(disagreement_id, row["state"], to_state, note, conn)
    _update_state(disagreement_id, to_state, conn)

    # Retain resolution note to Hindsight
    try:
        retain_resolution(disagreement_id, note, row["candidate_slug"])
    except Exception as e:
        print(f"WARNING: Hindsight retain failed for resolution: {e}")

    return _get_or_404(disagreement_id, conn)


def _retag_fact(fact_id: str, new_context: str, conn):
    """Update task_context, push old value to task_context_history."""
    import json
    row = conn.execute("SELECT task_context, task_context_history FROM facts WHERE fact_id=?", (fact_id,)).fetchone()
    history = json.loads(row["task_context_history"])
    history.append(row["task_context"])
    conn.execute(
        "UPDATE facts SET task_context=?, task_context_history=? WHERE fact_id=?",
        (new_context, json.dumps(history), fact_id)
    )
    conn.commit()
```

### Task 6.6 — `finalize(candidate_slug: str, conn) → dict`

```python
def finalize(candidate_slug: str, conn) -> dict:
    """
    Set candidate status=finalized.
    Move all non-RESOLVED disagreements to STILL_OPEN.
    Return final summary.
    """
    # Check already finalized
    candidate = conn.execute("SELECT status FROM candidates WHERE slug=?", (candidate_slug,)).fetchone()
    if not candidate:
        raise ValueError(f"Candidate {candidate_slug} not found")
    if candidate["status"] == "finalized":
        raise ValueError(f"Candidate {candidate_slug} is already finalized")

    now = datetime.utcnow().isoformat() + "Z"

    # Move non-RESOLVED to STILL_OPEN
    open_disgs = conn.execute(
        "SELECT * FROM disagreements WHERE candidate_slug=? AND state NOT IN ('RESOLVED','STILL_OPEN')",
        (candidate_slug,)
    ).fetchall()

    for d in open_disgs:
        _write_transition(d["disagreement_id"], d["state"], "STILL_OPEN", "Candidate finalized", conn)
        _update_state(d["disagreement_id"], "STILL_OPEN", conn)

    # Update candidate status
    conn.execute(
        "UPDATE candidates SET status='finalized', finalized_at=? WHERE slug=?",
        (now, candidate_slug)
    )
    conn.commit()

    # Build final summary
    all_disgs = conn.execute(
        "SELECT * FROM disagreements WHERE candidate_slug=?", (candidate_slug,)
    ).fetchall()

    return {
        "candidate_slug": candidate_slug,
        "finalized_at": now,
        "disagreements": [dict(d) for d in all_disgs],
        "still_open_count": sum(1 for d in all_disgs if d["state"] == "STILL_OPEN"),
        "resolved_count": sum(1 for d in all_disgs if d["state"] == "RESOLVED"),
    }
```

### Task 6.7 — `open_disagreements(candidate_slug: str, conn) → list`

```python
def open_disagreements(candidate_slug: str, conn) -> list:
    """Always from SQLite, never from Hindsight."""
    rows = conn.execute(
        "SELECT * FROM disagreements WHERE candidate_slug=? AND state NOT IN ('RESOLVED','STILL_OPEN')",
        (candidate_slug,)
    ).fetchall()
    return [dict(r) for r in rows]
```

### Task 6.8 — Helper functions

```python
def _get_or_404(disagreement_id: str, conn) -> dict:
    row = conn.execute("SELECT * FROM disagreements WHERE disagreement_id=?", (disagreement_id,)).fetchone()
    if not row:
        raise KeyError(f"Disagreement {disagreement_id} not found")
    return dict(row)

def _write_transition(disagreement_id, from_state, to_state, note, conn):
    from app.memory import retain_transition
    now = datetime.utcnow().isoformat() + "Z"
    tid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO transitions (transition_id, disagreement_id, from_state, to_state, note, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (tid, disagreement_id, from_state, to_state, note, now)
    )
    conn.commit()
    # Mirror to Hindsight (best-effort)
    try:
        d = conn.execute("SELECT candidate_slug FROM disagreements WHERE disagreement_id=?", (disagreement_id,)).fetchone()
        retain_transition(disagreement_id, to_state, note, d["candidate_slug"])
    except Exception:
        pass

def _update_state(disagreement_id, new_state, conn):
    now = datetime.utcnow().isoformat() + "Z"
    conn.execute(
        "UPDATE disagreements SET state=?, updated_at=? WHERE disagreement_id=?",
        (new_state, now, disagreement_id)
    )
    conn.commit()
```

---

## Wave 2 — Tests for Phase 6

File: `tests/test_lifecycle.py`

```python
import pytest, sqlite3, uuid
from app.db import create_tables
from app.lifecycle import (
    create_disagreement, mark_probe_asked, submit_resolution,
    finalize, open_disagreements, InvalidTransition
)

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_tables(c)
    # Seed: candidate, submission, 2 facts, pair_verdict
    now = "2024-01-01T00:00:00Z"
    c.execute("INSERT INTO candidates VALUES (?,?,?,?,?)", ("alice","Alice","open",now,None))
    sub_id = str(uuid.uuid4())
    c.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)",
              (sub_id,"alice","iv1","IV1",1,"behavioral",0,"text",now))
    sub_id2 = str(uuid.uuid4())
    c.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)",
              (sub_id2,"alice","iv2","IV2",2,"behavioral",0,"text",now))
    fa_id, fb_id = str(uuid.uuid4()), str(uuid.uuid4())
    c.execute("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (fa_id,sub_id,"alice","iv1",1,"Alice showed poor design","poor design","system_design","negative","behavioral","[]",0,1,now))
    c.execute("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (fb_id,sub_id2,"alice","iv2",2,"Alice showed excellent design","excellent design","system_design","positive","behavioral","[]",0,1,now))
    pair_id = str(uuid.uuid4())
    c.execute("INSERT INTO pair_verdicts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (pair_id,"alice","system_design",fa_id,fb_id,"CONTRADICTION","stage3_rules",1,0,1,0.9,"rationale","llm",None,now))
    c.commit()
    yield c, fa_id, fb_id, pair_id
    c.close()

def make_pv(conn_data):
    c, fa_id, fb_id, pair_id = conn_data
    return {
        "pair_id": pair_id,
        "candidate_slug": "alice",
        "competency": "system_design",
        "kind": "CONTRADICTION",
        "fact_a": {"fact_id": fa_id, "interviewer_id": "iv1", "round": 1,
                   "claim_normalized": "Alice showed poor design", "task_context": "behavioral"},
        "fact_b": {"fact_id": fb_id, "interviewer_id": "iv2", "round": 2,
                   "claim_normalized": "Alice showed excellent design", "task_context": "behavioral"},
    }

def test_create_disagreement(conn):
    c, *_ = conn
    from unittest.mock import patch
    with patch("app.synthesis.follow_up", return_value="Ask about scaling."):
        d = create_disagreement(make_pv(conn), c)
    assert d["state"] == "RAISED"
    assert d["competency"] == "system_design"

def test_create_disagreement_idempotent(conn):
    c, *_ = conn
    with patch("app.synthesis.follow_up", return_value="Ask about scaling."):
        d1 = create_disagreement(make_pv(conn), c)
        d2 = create_disagreement(make_pv(conn), c)
    assert d1["disagreement_id"] == d2["disagreement_id"]

def test_mark_probe_asked(conn):
    c, *_ = conn
    with patch("app.synthesis.follow_up", return_value="Q"):
        d = create_disagreement(make_pv(conn), c)
    updated = mark_probe_asked(d["disagreement_id"], c)
    assert updated["state"] == "PROBE_ASKED"

def test_invalid_transition_raises(conn):
    c, *_ = conn
    with patch("app.synthesis.follow_up", return_value="Q"):
        d = create_disagreement(make_pv(conn), c)
    # RAISED → STILL_OPEN is not allowed directly
    with pytest.raises(InvalidTransition):
        from app.lifecycle import _assert_transition
        _assert_transition("RAISED", "STILL_OPEN")

def test_resolution_confirms_a_resolves(conn):
    c, *_ = conn
    with patch("app.synthesis.follow_up", return_value="Q"):
        d = create_disagreement(make_pv(conn), c)
    updated = submit_resolution(d["disagreement_id"], "CONFIRMS_CLAIM_A", "Follow-up confirmed claim A", None, None, c)
    assert updated["state"] == "RESOLVED"

def test_resolution_unclear_escalates(conn):
    c, *_ = conn
    with patch("app.synthesis.follow_up", return_value="Q"):
        d = create_disagreement(make_pv(conn), c)
    updated = submit_resolution(d["disagreement_id"], "UNCLEAR", "Response was ambiguous here", None, None, c)
    assert updated["state"] == "ESCALATED"

def test_resolution_both_hold_requires_contexts(conn):
    c, *_ = conn
    with patch("app.synthesis.follow_up", return_value="Q"):
        d = create_disagreement(make_pv(conn), c)
    with pytest.raises(ValueError):
        submit_resolution(d["disagreement_id"], "BOTH_HOLD_UNDER_DIFFERENT_CONTEXT",
                          "Both contexts identified", None, None, c)

def test_finalize_moves_unresolved_to_still_open(conn):
    c, *_ = conn
    with patch("app.synthesis.follow_up", return_value="Q"):
        create_disagreement(make_pv(conn), c)
    result = finalize("alice", c)
    assert result["still_open_count"] == 1
    assert result["resolved_count"] == 0

def test_resolved_not_moved_on_finalize(conn):
    c, *_ = conn
    with patch("app.synthesis.follow_up", return_value="Q"):
        d = create_disagreement(make_pv(conn), c)
    submit_resolution(d["disagreement_id"], "CONFIRMS_CLAIM_A", "Confirmed in follow-up session", None, None, c)
    result = finalize("alice", c)
    assert result["resolved_count"] == 1
    assert result["still_open_count"] == 0

def test_no_resolution_copy_contains_banned_phrases(conn):
    from app.synthesis import lint_text
    resolution_labels = [
        "The follow-up response is consistent with Claim A",
        "The follow-up response is consistent with Claim B",
        "Both claims hold, under different conditions",
        "New information came up that is not yet resolved",
        "The response did not clearly settle it",
    ]
    for label in resolution_labels:
        violations = lint_text(label)
        assert not violations, f"Resolution label failed lint: '{label}' → {violations}"
```

---

## Acceptance Verification

| Check | Command | Expected |
|---|---|---|
| All lifecycle tests | `pytest tests/test_lifecycle.py -v` | All 10 pass |
| Each resolution → correct state | `test_resolution_*` | RESOLVED or ESCALATED correctly |
| Invalid transition raises | `test_invalid_transition_raises` | InvalidTransition raised |
| Finalize STILL_OPEN | `test_finalize_moves_unresolved_to_still_open` | still_open_count=1 |
| No duplicate disagreements | `test_create_disagreement_idempotent` | Same ID returned |
| Resolution labels lint-clean | `test_no_resolution_copy_contains_banned_phrases` | All pass |

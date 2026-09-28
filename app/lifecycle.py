"""app/lifecycle.py — Disagreement Lifecycle and Resolution."""
import uuid
from datetime import datetime

class InvalidTransition(Exception):
    """Raised when a state transition is not in the allowed set."""
    pass

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "RAISED":      {"PROBE_ASKED", "RESOLVED", "ESCALATED"},
    "PROBE_ASKED": {"RESOLVED", "ESCALATED"},
    "ESCALATED":   {"PROBE_ASKED", "RESOLVED"},
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

def create_disagreement(pair_verdict: dict, conn) -> dict:
    """
    Create a disagreement row for a CONTRADICTION or CONTEXT_SPLIT pair.
    Idempotent: if one already exists for this (slug, comp, ivr_a, ivr_b, kind), do nothing.
    Returns the existing or newly created disagreement dict.
    """
    from app.memory import retain_transition

    fact_a = pair_verdict["fact_a"]
    slug = pair_verdict.get("candidate_slug", fact_a["candidate_slug"])
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
        print(f"WARNING: Hindsight retain failed for transition {transition_id}: {e}")

    return dict(conn.execute(
        "SELECT * FROM disagreements WHERE disagreement_id=?", (disagreement_id,)
    ).fetchone())

def mark_probe_asked(disagreement_id: str, conn) -> dict:
    row = _get_or_404(disagreement_id, conn)
    _assert_transition(row["state"], "PROBE_ASKED")
    _write_transition(disagreement_id, row["state"], "PROBE_ASKED", "Probe marked as asked", conn)
    _update_state(disagreement_id, "PROBE_ASKED", conn)
    return _get_or_404(disagreement_id, conn)

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
        # Retro-tag both facts
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

def finalize(candidate_slug: str, conn) -> dict:
    """
    Set candidate status=finalized.
    Move all non-RESOLVED disagreements to STILL_OPEN.
    Return final summary.
    """
    candidate = conn.execute("SELECT status FROM candidates WHERE slug=?", (candidate_slug,)).fetchone()
    if not candidate:
        raise ValueError(f"Candidate {candidate_slug} not found")
    if candidate["status"] == "finalized":
        raise ValueError(f"Candidate {candidate_slug} is already finalized")

    now = datetime.utcnow().isoformat() + "Z"

    open_disgs = conn.execute(
        "SELECT * FROM disagreements WHERE candidate_slug=? AND state NOT IN ('RESOLVED','STILL_OPEN')",
        (candidate_slug,)
    ).fetchall()

    for d in open_disgs:
        _write_transition(d["disagreement_id"], d["state"], "STILL_OPEN", "Candidate finalized", conn)
        _update_state(d["disagreement_id"], "STILL_OPEN", conn)

    conn.execute(
        "UPDATE candidates SET status='finalized', finalized_at=? WHERE slug=?",
        (now, candidate_slug)
    )
    conn.commit()

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

def open_disagreements(candidate_slug: str, conn) -> list:
    rows = conn.execute(
        "SELECT * FROM disagreements WHERE candidate_slug=? AND state NOT IN ('RESOLVED','STILL_OPEN')",
        (candidate_slug,)
    ).fetchall()
    return [dict(r) for r in rows]

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

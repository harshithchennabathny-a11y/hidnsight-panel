"""tests/test_lifecycle.py — Offline lifecycle tests.

All Hindsight calls and Groq calls are patched so these tests run
without network access.
"""
import pytest
import sqlite3
import uuid
from contextlib import ExitStack
from unittest.mock import patch, MagicMock

from app.db import create_tables
from app.lifecycle import (
    create_disagreement, mark_probe_asked, submit_resolution,
    finalize, open_disagreements, InvalidTransition,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_tables(c)
    # Seed: candidate, 2 submissions, 2 facts, 1 pair_verdict
    now = "2024-01-01T00:00:00Z"
    c.execute("INSERT INTO candidates VALUES (?,?,?,?,?)", ("alice", "Alice", "open", now, None))
    sub_id = str(uuid.uuid4())
    c.execute(
        "INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)",
        (sub_id, "alice", "iv1", "IV1", 1, "behavioral", 0, "text", now),
    )
    sub_id2 = str(uuid.uuid4())
    c.execute(
        "INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)",
        (sub_id2, "alice", "iv2", "IV2", 2, "behavioral", 0, "text", now),
    )
    fa_id, fb_id = str(uuid.uuid4()), str(uuid.uuid4())
    c.execute(
        "INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fa_id, sub_id, "alice", "iv1", 1, "Alice showed poor design", "poor design",
         "system_design", "negative", "behavioral", "[]", 0, 1, now),
    )
    c.execute(
        "INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fb_id, sub_id2, "alice", "iv2", 2, "Alice showed excellent design", "excellent design",
         "system_design", "positive", "behavioral", "[]", 0, 1, now),
    )
    pair_id = str(uuid.uuid4())
    c.execute(
        "INSERT INTO pair_verdicts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (pair_id, "alice", "system_design", fa_id, fb_id, "CONTRADICTION",
         "stage3_rules", 1, 0, 1, 0.9, "rationale", "llm", None, now),
    )
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
        "fact_a": {
            "fact_id": fa_id,
            "interviewer_id": "iv1",
            "round": 1,
            "claim_normalized": "Alice showed poor design",
            "task_context": "behavioral",
        },
        "fact_b": {
            "fact_id": fb_id,
            "interviewer_id": "iv2",
            "round": 2,
            "claim_normalized": "Alice showed excellent design",
            "task_context": "behavioral",
        },
    }


def _mock_patches():
    """ExitStack that silences all external I/O during lifecycle tests."""
    stack = ExitStack()
    stack.enter_context(patch("app.synthesis.follow_up", return_value="Ask about scaling."))
    stack.enter_context(patch("app.memory.retain_transition", MagicMock()))
    stack.enter_context(patch("app.memory.retain_resolution", MagicMock()))
    stack.enter_context(patch("app.memory.hindsight_client", MagicMock()))
    return stack


def test_create_disagreement(conn):
    c, *_ = conn
    with _mock_patches():
        d = create_disagreement(make_pv(conn), c)
    assert d["state"] == "RAISED"
    assert d["competency"] == "system_design"


def test_create_disagreement_idempotent(conn):
    c, *_ = conn
    with _mock_patches():
        d1 = create_disagreement(make_pv(conn), c)
        d2 = create_disagreement(make_pv(conn), c)
    assert d1["disagreement_id"] == d2["disagreement_id"]


def test_mark_probe_asked(conn):
    c, *_ = conn
    with _mock_patches():
        d = create_disagreement(make_pv(conn), c)
        updated = mark_probe_asked(d["disagreement_id"], c)
    assert updated["state"] == "PROBE_ASKED"


def test_invalid_transition_raises(conn):
    c, *_ = conn
    with _mock_patches():
        create_disagreement(make_pv(conn), c)
    with pytest.raises(InvalidTransition):
        from app.lifecycle import _assert_transition
        _assert_transition("RAISED", "STILL_OPEN")


def test_resolution_confirms_a_resolves(conn):
    c, *_ = conn
    with _mock_patches():
        d = create_disagreement(make_pv(conn), c)
        updated = submit_resolution(
            d["disagreement_id"], "CONFIRMS_CLAIM_A",
            "Follow-up confirmed claim A", None, None, c,
        )
    assert updated["state"] == "RESOLVED"


def test_resolution_unclear_escalates(conn):
    c, *_ = conn
    with _mock_patches():
        d = create_disagreement(make_pv(conn), c)
        updated = submit_resolution(
            d["disagreement_id"], "UNCLEAR",
            "Response was ambiguous here", None, None, c,
        )
    assert updated["state"] == "ESCALATED"


def test_resolution_both_hold_requires_contexts(conn):
    c, *_ = conn
    with _mock_patches():
        d = create_disagreement(make_pv(conn), c)
        with pytest.raises(ValueError):
            submit_resolution(
                d["disagreement_id"], "BOTH_HOLD_UNDER_DIFFERENT_CONTEXT",
                "Both contexts identified", None, None, c,
            )


def test_finalize_moves_unresolved_to_still_open(conn):
    c, *_ = conn
    with _mock_patches():
        create_disagreement(make_pv(conn), c)
        result = finalize("alice", c)
    assert result["still_open_count"] == 1
    assert result["resolved_count"] == 0


def test_resolved_not_moved_on_finalize(conn):
    c, *_ = conn
    with _mock_patches():
        d = create_disagreement(make_pv(conn), c)
        submit_resolution(
            d["disagreement_id"], "CONFIRMS_CLAIM_A",
            "Confirmed in follow-up session", None, None, c,
        )
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

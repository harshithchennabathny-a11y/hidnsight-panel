"""tests/test_live_vs_mocked.py — Split-mode drift detection.

Runs the same pipeline input (Fixture 1: obvious contradiction) through:
  A. MOCKED mode  — Hindsight patched, no network calls (always runs)
  B. LIVE mode    — Real Hindsight client, ephemeral bank  (@pytest.mark.live)

Both modes must agree on:
  - verdict == CONTRADICTION
  - verdict_path == stage3_rules
  - a disagreement_id is created
  - lifecycle_state == RAISED

If A passes but B fails, the failure is in the live Hindsight API or network.
If B passes but A fails, the failure is in the mock setup.
If both fail, the failure is in pipeline logic.
"""
import sqlite3
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.db import create_tables
from app.enums import Competency, Verdict, VerdictPath, LifecycleState
from app.synthesis import evaluate_candidate


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers (identical setup for both modes)
# ─────────────────────────────────────────────────────────────────────────────

def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    create_tables(conn)
    return conn


def _seed(conn: sqlite3.Connection, slug: str) -> None:
    """Seed Fixture 1 (obvious contradiction) into the given DB."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO candidates (slug, display_name, status, created_at) VALUES (?, ?, 'open', ?)",
        (slug, "Drift Candidate", now),
    )
    conn.commit()

    for interviewer, polarity, claim, span in [
        (
            "interviewer_a",
            "positive",
            "The candidate proposed an excellent distributed caching and sharding design.",
            "excellent distributed caching and sharding design",
        ),
        (
            "interviewer_b",
            "negative",
            "The candidate failed to consider data scaling and proposed an unscalable monolith.",
            "failed to consider data scaling and proposed an unscalable monolith",
        ),
    ]:
        sub_id = str(uuid.uuid4())
        fact_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO submissions
               (submission_id, candidate_slug, interviewer_id, interviewer_name, round,
                task_context, reviewed_others_notes, raw_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
            (sub_id, slug, interviewer, interviewer.capitalize(), 1,
             "whiteboard_design", f"Raw text: {span}", now),
        )
        conn.execute(
            """INSERT INTO facts
               (fact_id, submission_id, candidate_slug, interviewer_id, round,
                claim_normalized, evidence_span, competency, polarity, task_context,
                task_context_history, reviewed_others_notes, mirrored, created_at)
               VALUES (?, ?, ?, ?, 1, ?, ?, 'system_design', ?, 'whiteboard_design',
                       '[]', 0, 1, ?)""",
            (fact_id, sub_id, slug, interviewer, claim, span, polarity, now),
        )
    conn.commit()


def _assert_obvious_contradiction(resp, mode: str) -> None:
    """Common assertions for Fixture 1 in any mode."""
    analyses = [a for a in resp.competency_analyses if a.competency == Competency.system_design]
    assert analyses, f"[{mode}] No system_design competency analysis found"
    a = analyses[0]
    assert a.verdict == Verdict.CONTRADICTION, \
        f"[{mode}] Expected CONTRADICTION, got {a.verdict}"
    assert a.verdict_path == VerdictPath.stage3_rules, \
        f"[{mode}] Expected stage3_rules, got {a.verdict_path}"
    assert a.disagreement_id is not None, \
        f"[{mode}] Expected a disagreement_id, got None"
    assert a.lifecycle_state == LifecycleState.RAISED, \
        f"[{mode}] Expected RAISED, got {a.lifecycle_state}"
    assert len(resp.open_disagreements_summary) >= 1, \
        f"[{mode}] Expected at least one open disagreement"


# ─────────────────────────────────────────────────────────────────────────────
# Mode A: MOCKED  (always runs, no env vars needed)
# ─────────────────────────────────────────────────────────────────────────────

def test_fixture1_mocked_mode(mock_hindsight):
    """Fixture 1 in fully-mocked mode — no network calls permitted."""
    slug = f"drift-mock-{uuid.uuid4().hex[:6]}"
    conn = _make_db()
    _seed(conn, slug)

    with patch("app.classify.nli_scores", return_value=0.92), \
         patch("app.synthesis.follow_up", return_value="Probe scale discrepancy."), \
         patch("app.memory.retain_transition"):
        resp = evaluate_candidate(slug, conn)

    _assert_obvious_contradiction(resp, "mocked")


# ─────────────────────────────────────────────────────────────────────────────
# Mode B: LIVE  (requires HINDSIGHT_API_KEY; skips cleanly if absent)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.live
def test_fixture1_live_mode(live_bank_id):
    """Fixture 1 against the real Hindsight API.

    Uses an ephemeral bank so it never touches real candidate data.
    Skips cleanly if HINDSIGHT_API_KEY is not set.
    """
    slug = live_bank_id  # e.g. "test-a3f7b2c1"
    conn = _make_db()
    _seed(conn, slug)

    # NLI score is still mocked (we're testing Hindsight, not the NLI model).
    # Groq is also mocked; this test is live only for Hindsight retain/recall.
    with patch("app.classify.nli_scores", return_value=0.92), \
         patch("app.synthesis.follow_up", return_value="Probe scale discrepancy."):
        # NOTE: app.memory calls the real hindsight_client() here.
        resp = evaluate_candidate(slug, conn)

    _assert_obvious_contradiction(resp, "live")


# ─────────────────────────────────────────────────────────────────────────────
# Drift comparison: run both modes and compare core fields
# ─────────────────────────────────────────────────────────────────────────────

def _run_mocked(slug: str) -> dict:
    """Return key fields from the mocked pipeline run."""
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_client.retain.return_value = None
    mock_client.retain_batch.return_value = None

    conn = _make_db()
    _seed(conn, slug)

    with patch("app.config.hindsight_client", return_value=mock_client), \
         patch("app.classify.nli_scores", return_value=0.92), \
         patch("app.synthesis.follow_up", return_value="Probe scale discrepancy."), \
         patch("app.memory.retain_transition"):
        resp = evaluate_candidate(slug, conn)

    a = next(x for x in resp.competency_analyses if x.competency == Competency.system_design)
    return {
        "verdict": a.verdict,
        "verdict_path": a.verdict_path,
        "has_disagreement": a.disagreement_id is not None,
        "lifecycle_state": a.lifecycle_state,
    }


@pytest.mark.live
def test_mocked_vs_live_drift(live_bank_id):
    """Run the same input in both modes and assert the outputs agree.

    Failure modes:
      - mocked passes, live fails  → live API / network issue
      - live passes, mocked fails  → mock setup is wrong
      - both fail                  → pipeline logic bug
    """
    slug_mock = f"{live_bank_id}-mock"
    slug_live = live_bank_id

    mocked_result = _run_mocked(slug_mock)

    # Live run
    conn_live = _make_db()
    _seed(conn_live, slug_live)
    with patch("app.classify.nli_scores", return_value=0.92), \
         patch("app.synthesis.follow_up", return_value="Probe scale discrepancy."):
        live_resp = evaluate_candidate(slug_live, conn_live)

    live_a = next(
        x for x in live_resp.competency_analyses
        if x.competency == Competency.system_design
    )
    live_result = {
        "verdict": live_a.verdict,
        "verdict_path": live_a.verdict_path,
        "has_disagreement": live_a.disagreement_id is not None,
        "lifecycle_state": live_a.lifecycle_state,
    }

    assert mocked_result == live_result, (
        f"DRIFT DETECTED!\n"
        f"  Mocked: {mocked_result}\n"
        f"  Live:   {live_result}\n"
        "If mocked passes but live fails, investigate the Hindsight API or network."
    )

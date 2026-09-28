"""tests/test_validation_fixtures.py — Validation Requirements test suite.

Covers all 14 Section 7 pipeline fixtures and calibration fixtures:
- Contradiction-detection fixtures (1-9)
- Lifecycle fixtures (10-13)
- Baseline-comparison fixture (14)
- Calibration fixtures (thin sample suppression, phrasing check, structural impossibility)

Testing mode:
- Pure-logic tests: mock Hindsight memory and NLI scores, spy on Groq client.
- Tests for Stages 2, 2.5, 3 MUST NOT call the LLM — enforced by a Groq client spy.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.db import create_tables
from app.enums import (
    Competency,
    TaskContext,
    Polarity,
    Verdict,
    VerdictPath,
    DisagreementKind,
    LifecycleState,
    ResolutionType,
)
from app.synthesis import evaluate_candidate, lint_text
from app.lifecycle import (
    create_disagreement,
    submit_resolution,
    finalize,
)
from app.calibration import get_calibration_stats
from baseline_comparison.run_baselines import mock_llm_call, CANDIDATE_A_TEXT


# ─────────────────────────────────────────────────────────────────────────────
# Helper Fixtures & Test Setup
# ─────────────────────────────────────────────────────────────────────────────

def _make_db() -> sqlite3.Connection:
    """Create an in-memory SQLite database with canonical Panel schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    create_tables(conn)
    return conn


def _seed_candidate(conn: sqlite3.Connection, slug: str, name: str = "Test Candidate") -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO candidates (slug, display_name, status, created_at) VALUES (?, ?, 'open', ?)",
        (slug, name, now),
    )
    conn.commit()


def _seed_submission_and_fact(
    conn: sqlite3.Connection,
    candidate_slug: str,
    interviewer_id: str,
    round_num: int,
    competency: str,
    polarity: str,
    task_context: str,
    claim_normalized: str,
    evidence_span: str,
    reviewed_others_notes: bool = False,
) -> tuple[str, str]:
    """Helper to insert a valid submission and corresponding extracted fact."""
    now = datetime.now(timezone.utc).isoformat()
    sub_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO submissions
           (submission_id, candidate_slug, interviewer_id, interviewer_name, round,
            task_context, reviewed_others_notes, raw_text, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            sub_id,
            candidate_slug,
            interviewer_id,
            interviewer_id.capitalize(),
            round_num,
            task_context,
            int(reviewed_others_notes),
            f"Raw text containing: {evidence_span}",
            now,
        ),
    )

    fact_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO facts
           (fact_id, submission_id, candidate_slug, interviewer_id, round,
            claim_normalized, evidence_span, competency, polarity, task_context,
            task_context_history, reviewed_others_notes, mirrored, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, 1, ?)""",
        (
            fact_id,
            sub_id,
            candidate_slug,
            interviewer_id,
            round_num,
            claim_normalized,
            evidence_span,
            competency,
            polarity,
            task_context,
            int(reviewed_others_notes),
            now,
        ),
    )
    conn.commit()
    return sub_id, fact_id


def _seed_pair_verdict(conn: sqlite3.Connection, pair_verdict: dict) -> str:
    """Helper to insert a pair_verdict row satisfying foreign key constraints."""
    pid = pair_verdict.get("pair_id") or str(uuid.uuid4())
    pair_verdict["pair_id"] = pid
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO pair_verdicts
           (pair_id, candidate_slug, competency, fact_a_id, fact_b_id,
            verdict, verdict_path, independent, anchored_dissent,
            polarity_opposite, nli_contradiction_max, rationale,
            synthesis_source, follow_up, evaluated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, 1, 0.9, 'Rationale', 'template', 'Follow up', ?)""",
        (
            pid,
            pair_verdict["candidate_slug"],
            pair_verdict["competency"],
            pair_verdict["fact_a"]["fact_id"],
            pair_verdict["fact_b"]["fact_id"],
            pair_verdict.get("verdict", "CONTRADICTION"),
            pair_verdict.get("verdict_path", "stage3_rules"),
            now,
        ),
    )
    conn.commit()
    return pid


def _groq_spy_fail(*args, **kwargs):
    """Spy target that fails immediately if the Groq LLM is called."""
    pytest.fail("Groq LLM was unexpectedly called during pure-logic stages 2 / 2.5 / 3!")


# ─────────────────────────────────────────────────────────────────────────────
# Contradiction-Detection Fixtures (1-9)
# ─────────────────────────────────────────────────────────────────────────────

def test_fixture_01_obvious_contradiction():
    """1. Obvious contradiction"""
    # Pure-logic test: same context, opposite polarity, high NLI contradiction.
    # Stage 3 rules must decide CONTRADICTION without calling Groq.
    conn = _make_db()
    slug = "cand-01-obvious"
    _seed_candidate(conn, slug)

    _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1,
        competency="system_design", polarity="positive",
        task_context="whiteboard_design",
        claim_normalized="The candidate proposed an excellent distributed caching and sharding design.",
        evidence_span="excellent distributed caching and sharding design",
        reviewed_others_notes=False,
    )
    _seed_submission_and_fact(
        conn, slug, "interviewer_b", 2,
        competency="system_design", polarity="negative",
        task_context="whiteboard_design",
        claim_normalized="The candidate failed to consider data scaling and proposed an unscalable monolith.",
        evidence_span="failed to consider data scaling and proposed an unscalable monolith",
        reviewed_others_notes=False,
    )

    with patch("app.classify.nli_scores", return_value=0.92), \
         patch("app.config.groq_client", side_effect=_groq_spy_fail), \
         patch("app.synthesis.follow_up", return_value="Probe scale discrepancy."), \
         patch("app.memory.retain_transition"):
        resp = evaluate_candidate(slug, conn)

    analysis = next(a for a in resp.competency_analyses if a.competency == Competency.system_design)
    assert analysis.verdict == Verdict.CONTRADICTION
    assert analysis.verdict_path == VerdictPath.stage3_rules
    assert analysis.disagreement_id is not None
    assert analysis.lifecycle_state == LifecycleState.RAISED
    assert len(resp.open_disagreements_summary) == 1


def test_fixture_02_subtle_contradiction():
    """2. Subtle contradiction"""
    # Pure-logic test: nuanced conflict on concurrency locking vs race conditions.
    # Stage 3 rules must decide CONTRADICTION without calling Groq.
    conn = _make_db()
    slug = "cand-02-subtle"
    _seed_candidate(conn, slug)

    _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1,
        competency="concurrency", polarity="positive",
        task_context="live_coding",
        claim_normalized="The candidate synchronized shared state cleanly preventing race conditions.",
        evidence_span="synchronized shared state cleanly preventing race conditions",
        reviewed_others_notes=False,
    )
    _seed_submission_and_fact(
        conn, slug, "interviewer_b", 2,
        competency="concurrency", polarity="negative",
        task_context="live_coding",
        claim_normalized="The candidate introduced subtle thread contention leading to deadlock risks.",
        evidence_span="introduced subtle thread contention leading to deadlock risks",
        reviewed_others_notes=False,
    )

    with patch("app.classify.nli_scores", return_value=0.83), \
         patch("app.config.groq_client", side_effect=_groq_spy_fail), \
         patch("app.synthesis.follow_up", return_value="Probe locking strategy."), \
         patch("app.memory.retain_transition"):
        resp = evaluate_candidate(slug, conn)

    analysis = next(a for a in resp.competency_analyses if a.competency == Competency.concurrency)
    assert analysis.verdict == Verdict.CONTRADICTION
    assert analysis.verdict_path == VerdictPath.stage3_rules
    assert analysis.disagreement_id is not None


def test_fixture_03_same_meaning_paraphrase():
    """3. Same-meaning paraphrase (should NOT be a contradiction)"""
    # Pure-logic test: two interviewers describe clean communication with different words.
    # Same polarity, low NLI contradiction. Verdict must be COMPLEMENTARY, no disagreement.
    conn = _make_db()
    slug = "cand-03-paraphrase"
    _seed_candidate(conn, slug)

    _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1,
        competency="communication", polarity="positive",
        task_context="behavioral",
        claim_normalized="The candidate communicated technical reasoning clearly and concisely.",
        evidence_span="communicated technical reasoning clearly and concisely",
        reviewed_others_notes=False,
    )
    _seed_submission_and_fact(
        conn, slug, "interviewer_b", 2,
        competency="communication", polarity="positive",
        task_context="behavioral",
        claim_normalized="The candidate articulated thoughts in a well-structured, easy-to-follow manner.",
        evidence_span="articulated thoughts in a well-structured, easy-to-follow manner",
        reviewed_others_notes=False,
    )

    with patch("app.classify.nli_scores", return_value=0.08), \
         patch("app.config.groq_client", side_effect=_groq_spy_fail):
        resp = evaluate_candidate(slug, conn)

    analysis = next(a for a in resp.competency_analyses if a.competency == Competency.communication)
    assert analysis.verdict == Verdict.COMPLEMENTARY
    assert analysis.verdict_path == VerdictPath.stage3_rules
    assert analysis.disagreement_id is None
    assert len(resp.open_disagreements_summary) == 0


def test_fixture_04_different_competency():
    """4. Different competency (should not be compared at all)"""
    # Pure-logic test: facts on different competencies must never be paired.
    # Each competency has only 1 source -> INSUFFICIENT_EVIDENCE (single_source).
    conn = _make_db()
    slug = "cand-04-diff-comp"
    _seed_candidate(conn, slug)

    _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1,
        competency="system_design", polarity="positive",
        task_context="whiteboard_design",
        claim_normalized="Candidate understood distributed queues.",
        evidence_span="understood distributed queues",
        reviewed_others_notes=False,
    )
    _seed_submission_and_fact(
        conn, slug, "interviewer_b", 2,
        competency="algorithmic_optimization", polarity="negative",
        task_context="live_coding",
        claim_normalized="Candidate missed the dynamic programming subproblem.",
        evidence_span="missed the dynamic programming subproblem",
        reviewed_others_notes=False,
    )

    with patch("app.config.groq_client", side_effect=_groq_spy_fail):
        resp = evaluate_candidate(slug, conn)

    sys_analysis = next(a for a in resp.competency_analyses if a.competency == Competency.system_design)
    algo_analysis = next(a for a in resp.competency_analyses if a.competency == Competency.algorithmic_optimization)

    assert sys_analysis.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert sys_analysis.insufficiency_reason == "single_source"
    assert sys_analysis.verdict_path == VerdictPath.stage2_sufficiency

    assert algo_analysis.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert algo_analysis.insufficiency_reason == "single_source"
    assert algo_analysis.verdict_path == VerdictPath.stage2_sufficiency


def test_fixture_05_polite_hedge_disagreement():
    """5. Polite-hedge disagreement"""
    # Pure-logic test: hedged negative assessment ("could be sharper") vs positive assessment.
    # Opposite polarity in same context with strong NLI -> CONTRADICTION via stage3_rules.
    conn = _make_db()
    slug = "cand-05-hedged"
    _seed_candidate(conn, slug)

    _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1,
        competency="product_sense", polarity="positive",
        task_context="system_design_discussion",
        claim_normalized="The candidate demonstrated excellent tradeoff reasoning for end-user metrics.",
        evidence_span="demonstrated excellent tradeoff reasoning for end-user metrics",
        reviewed_others_notes=False,
    )
    _seed_submission_and_fact(
        conn, slug, "interviewer_b", 2,
        competency="product_sense", polarity="negative",
        task_context="system_design_discussion",
        claim_normalized="The candidate could be sharper on product tradeoffs and lacked depth.",
        evidence_span="could be sharper on product tradeoffs and lacked depth",
        reviewed_others_notes=False,
    )

    with patch("app.classify.nli_scores", return_value=0.86), \
         patch("app.config.groq_client", side_effect=_groq_spy_fail), \
         patch("app.synthesis.follow_up", return_value="Probe depth of product tradeoffs."), \
         patch("app.memory.retain_transition"):
        resp = evaluate_candidate(slug, conn)

    analysis = next(a for a in resp.competency_analyses if a.competency == Competency.product_sense)
    assert analysis.verdict == Verdict.CONTRADICTION
    assert analysis.verdict_path == VerdictPath.stage3_rules
    assert analysis.disagreement_id is not None


def test_fixture_06_temporal_progression_context_mismatch():
    """6. Temporal progression via context mismatch"""
    # Pure-logic test: round 1 live coding struggle vs round 2 whiteboard discussion success.
    # Different context AND opposite polarity -> Stage 2.5 context routing: CONDITIONAL_BOTH_APPLY (CONTEXT_SPLIT).
    conn = _make_db()
    slug = "cand-06-temporal"
    _seed_candidate(conn, slug)

    _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1,
        competency="system_design", polarity="negative",
        task_context="live_coding",
        claim_normalized="The candidate struggled with system architecture during live coding.",
        evidence_span="struggled with system architecture during live coding",
        reviewed_others_notes=False,
    )
    _seed_submission_and_fact(
        conn, slug, "interviewer_b", 2,
        competency="system_design", polarity="positive",
        task_context="system_design_discussion",
        claim_normalized="The candidate excelled at explaining large-scale architecture in discussion.",
        evidence_span="excelled at explaining large-scale architecture in discussion",
        reviewed_others_notes=False,
    )

    with patch("app.config.groq_client", side_effect=_groq_spy_fail), \
         patch("app.synthesis.follow_up", return_value="Was format live coding vs discussion the difference?"), \
         patch("app.memory.retain_transition"):
        resp = evaluate_candidate(slug, conn)

    analysis = next(a for a in resp.competency_analyses if a.competency == Competency.system_design)
    assert analysis.verdict == Verdict.CONDITIONAL_BOTH_APPLY
    assert analysis.verdict_path == VerdictPath.stage2_5_context
    assert analysis.disagreement_id is not None
    # Confirm kind in disagreements table is CONTEXT_SPLIT
    d_row = conn.execute("SELECT kind FROM disagreements WHERE disagreement_id=?", (analysis.disagreement_id,)).fetchone()
    assert d_row["kind"] == "CONTEXT_SPLIT"


def test_fixture_07_same_round_context_mismatch():
    """7. Same-round context mismatch"""
    # Pure-logic test: same round (round 1), but different task context (pair_programming vs take_home_review).
    # Opposite polarity -> Stage 2.5 context routing: CONDITIONAL_BOTH_APPLY (CONTEXT_SPLIT).
    conn = _make_db()
    slug = "cand-07-same-round"
    _seed_candidate(conn, slug)

    _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1,
        competency="concurrency", polarity="negative",
        task_context="pair_programming",
        claim_normalized="The candidate struggled with thread safety during pair programming.",
        evidence_span="struggled with thread safety during pair programming",
        reviewed_others_notes=False,
    )
    _seed_submission_and_fact(
        conn, slug, "interviewer_b", 1,
        competency="concurrency", polarity="positive",
        task_context="take_home_review",
        claim_normalized="The candidate demonstrated excellent thread safety in take-home code.",
        evidence_span="demonstrated excellent thread safety in take-home code",
        reviewed_others_notes=False,
    )

    with patch("app.config.groq_client", side_effect=_groq_spy_fail), \
         patch("app.synthesis.follow_up", return_value="Compare pair programming vs take-home environments."), \
         patch("app.memory.retain_transition"):
        resp = evaluate_candidate(slug, conn)

    analysis = next(a for a in resp.competency_analyses if a.competency == Competency.concurrency)
    assert analysis.verdict == Verdict.CONDITIONAL_BOTH_APPLY
    assert analysis.verdict_path == VerdictPath.stage2_5_context
    assert analysis.disagreement_id is not None


def test_fixture_08_anchored_pair_insufficiency():
    """8. Anchored-pair insufficiency (reviewed_others_notes demotes the count)"""
    # Pure-logic test: two interviewers agree (same polarity), but interviewer_b read notes first.
    # All pairs are anchored agreement -> INSUFFICIENT_EVIDENCE (anchored_agreement_only).
    conn = _make_db()
    slug = "cand-08-anchored"
    _seed_candidate(conn, slug)

    _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1,
        competency="system_design", polarity="positive",
        task_context="whiteboard_design",
        claim_normalized="System design was solid and scalable.",
        evidence_span="System design was solid and scalable",
        reviewed_others_notes=False,
    )
    _seed_submission_and_fact(
        conn, slug, "interviewer_b", 2,
        competency="system_design", polarity="positive",
        task_context="whiteboard_design",
        claim_normalized="Concurred that system design was solid and scalable.",
        evidence_span="Concurred that system design was solid and scalable",
        reviewed_others_notes=True,  # Anchored!
    )

    with patch("app.config.groq_client", side_effect=_groq_spy_fail):
        resp = evaluate_candidate(slug, conn)

    analysis = next(a for a in resp.competency_analyses if a.competency == Competency.system_design)
    assert analysis.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert analysis.insufficiency_reason == "anchored_agreement_only"
    assert analysis.verdict_path == VerdictPath.stage2_sufficiency
    assert analysis.disagreement_id is None


def test_fixture_09_ambiguous_nli_case_escalates_to_stage4():
    """9. Ambiguous-NLI case that must escalate to stage4_llm_adjudicated"""
    # Live-integration / Stage 4 test: signals split (opposite polarity, but contradiction score is below threshold).
    # Decision table rule 3b escalates to Stage 4 LLM adjudication.
    conn = _make_db()
    slug = "cand-09-ambiguous"
    _seed_candidate(conn, slug)

    _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1,
        competency="concurrency", polarity="positive",
        task_context="live_coding",
        claim_normalized="The candidate handled async tasks with minimal complexity.",
        evidence_span="handled async tasks with minimal complexity",
        reviewed_others_notes=False,
    )
    _seed_submission_and_fact(
        conn, slug, "interviewer_b", 2,
        competency="concurrency", polarity="negative",
        task_context="live_coding",
        claim_normalized="The candidate avoided async patterns and used blocking calls.",
        evidence_span="avoided async patterns and used blocking calls",
        reviewed_others_notes=False,
    )

    mock_llm_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "verdict": "CONTRADICTION",
        "rationale": "Claim A (interviewer_a, round 1) and Claim B (interviewer_b, round 2) directly conflict on concurrency approach."
    })
    mock_choice.finish_reason = "stop"
    mock_llm_response.choices = [mock_choice]

    mock_groq_client = MagicMock()
    mock_groq_client.chat.completions.create.return_value = mock_llm_response

    # Ambiguous NLI: opposite polarity but c=0.55 (< HIGH 0.80)
    with patch("app.classify.nli_scores", return_value=0.55), \
         patch("app.synthesis.groq_client", return_value=mock_groq_client), \
         patch("app.synthesis.follow_up", return_value="Probe concurrency approach."), \
         patch("app.memory.retain_transition"):
        resp = evaluate_candidate(slug, conn)

    analysis = next(a for a in resp.competency_analyses if a.competency == Competency.concurrency)
    assert analysis.verdict == Verdict.CONTRADICTION
    assert analysis.verdict_path == VerdictPath.stage4_llm
    # Assert Groq client was indeed called to adjudicate
    assert mock_groq_client.chat.completions.create.called


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle Fixtures (10-13)
# ─────────────────────────────────────────────────────────────────────────────

def test_fixture_10_raised_contradiction_resolution_confirms_claim_a():
    """10. RAISED contradiction + resolution confirming claim A -> RESOLVED, assert the output text does NOT contain "was right", "was wrong", or "more accurate" """
    conn = _make_db()
    slug = "cand-10-lifecycle"
    _seed_candidate(conn, slug)

    _, fact_a_id = _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1, "system_design", "positive", "whiteboard_design",
        "Scale handling was strong.", "Scale handling was strong"
    )
    _, fact_b_id = _seed_submission_and_fact(
        conn, slug, "interviewer_b", 2, "system_design", "negative", "whiteboard_design",
        "Scale handling was inadequate.", "Scale handling was inadequate"
    )

    pair_verdict = {
        "candidate_slug": slug,
        "competency": "system_design",
        "kind": "CONTRADICTION",
        "pair_id": str(uuid.uuid4()),
        "fact_a": {"fact_id": fact_a_id, "interviewer_id": "interviewer_a", "round": 1, "task_context": "whiteboard_design", "competency": "system_design", "claim_normalized": "Claim A"},
        "fact_b": {"fact_id": fact_b_id, "interviewer_id": "interviewer_b", "round": 2, "task_context": "whiteboard_design", "competency": "system_design", "claim_normalized": "Claim B"},
    }

    _seed_pair_verdict(conn, pair_verdict)

    with patch("app.memory.retain_transition"), \
         patch("app.synthesis.follow_up", return_value="Probe scale discrepancy."), \
         patch("app.memory.retain_resolution"):
        disg = create_disagreement(pair_verdict, conn)
        assert disg["state"] == LifecycleState.RAISED

        resolution_note = "The follow-up response is consistent with Claim A observations on distributed scale."
        updated = submit_resolution(
            disagreement_id=disg["disagreement_id"],
            resolution_type=ResolutionType.CONFIRMS_CLAIM_A,
            note=resolution_note,
            context_a=None,
            context_b=None,
            conn=conn,
        )

    assert updated["state"] == LifecycleState.RESOLVED

    # Assert transition logs and resolution notes do NOT contain banned comparative phrases
    transitions = conn.execute(
        "SELECT * FROM transitions WHERE disagreement_id=?", (disg["disagreement_id"],)
    ).fetchall()
    all_texts = [resolution_note] + [t["note"] for t in transitions if t["note"]]

    for t_text in all_texts:
        violations = lint_text(t_text)
        assert not violations, f"Text failed lint: {t_text}"
        assert "was right" not in t_text.lower()
        assert "was wrong" not in t_text.lower()
        assert "more accurate" not in t_text.lower()


def test_fixture_11_raised_contradiction_resolution_revealing_uncaptured_context():
    """11. RAISED contradiction + resolution revealing an uncaptured task_context -> RESOLVED, assert both original facts get retagged"""
    conn = _make_db()
    slug = "cand-11-retag"
    _seed_candidate(conn, slug)

    _, fact_a_id = _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1, "system_design", "positive", "whiteboard_design",
        "Handled architecture cleanly.", "Handled architecture cleanly"
    )
    _, fact_b_id = _seed_submission_and_fact(
        conn, slug, "interviewer_b", 2, "system_design", "negative", "whiteboard_design",
        "Struggled with microservice boundaries.", "Struggled with microservice boundaries"
    )

    pair_verdict = {
        "candidate_slug": slug,
        "competency": "system_design",
        "kind": "CONTRADICTION",
        "pair_id": str(uuid.uuid4()),
        "fact_a": {"fact_id": fact_a_id, "interviewer_id": "interviewer_a", "round": 1, "task_context": "whiteboard_design", "competency": "system_design", "claim_normalized": "Claim A"},
        "fact_b": {"fact_id": fact_b_id, "interviewer_id": "interviewer_b", "round": 2, "task_context": "whiteboard_design", "competency": "system_design", "claim_normalized": "Claim B"},
    }

    _seed_pair_verdict(conn, pair_verdict)

    with patch("app.memory.retain_transition"), \
         patch("app.synthesis.follow_up", return_value="Probe architecture scope."), \
         patch("app.memory.retain_resolution"):
        disg = create_disagreement(pair_verdict, conn)
        submit_resolution(
            disagreement_id=disg["disagreement_id"],
            resolution_type=ResolutionType.BOTH_HOLD_UNDER_DIFFERENT_CONTEXT,
            note="Interviewer A probed distributed discussion while Interviewer B evaluated live coding implementation.",
            context_a=TaskContext.system_design_discussion,
            context_b=TaskContext.live_coding,
            conn=conn,
        )

    # Verify both facts get retro-tagged with new context and old context saved to history
    row_a = conn.execute("SELECT task_context, task_context_history FROM facts WHERE fact_id=?", (fact_a_id,)).fetchone()
    row_b = conn.execute("SELECT task_context, task_context_history FROM facts WHERE fact_id=?", (fact_b_id,)).fetchone()

    assert row_a["task_context"] == TaskContext.system_design_discussion
    assert "whiteboard_design" in json.loads(row_a["task_context_history"])

    assert row_b["task_context"] == TaskContext.live_coding
    assert "whiteboard_design" in json.loads(row_b["task_context_history"])


def test_fixture_12_raised_contradiction_resolution_new_unresolved_info():
    """12. RAISED contradiction + resolution introducing new unresolved info -> ESCALATED"""
    conn = _make_db()
    slug = "cand-12-escalated"
    _seed_candidate(conn, slug)

    _, fact_a_id = _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1, "algorithmic_optimization", "positive", "live_coding",
        "Algorithm was O(N log N).", "Algorithm was O(N log N)"
    )
    _, fact_b_id = _seed_submission_and_fact(
        conn, slug, "interviewer_b", 2, "algorithmic_optimization", "negative", "live_coding",
        "Algorithm degraded to O(N^2).", "Algorithm degraded to O(N^2)"
    )

    pair_verdict = {
        "candidate_slug": slug,
        "competency": "algorithmic_optimization",
        "kind": "CONTRADICTION",
        "pair_id": str(uuid.uuid4()),
        "fact_a": {"fact_id": fact_a_id, "interviewer_id": "interviewer_a", "round": 1, "task_context": "live_coding", "competency": "algorithmic_optimization", "claim_normalized": "Claim A"},
        "fact_b": {"fact_id": fact_b_id, "interviewer_id": "interviewer_b", "round": 2, "task_context": "live_coding", "competency": "algorithmic_optimization", "claim_normalized": "Claim B"},
    }

    _seed_pair_verdict(conn, pair_verdict)

    with patch("app.memory.retain_transition"), \
         patch("app.synthesis.follow_up", return_value="Probe complexity."), \
         patch("app.memory.retain_resolution"):
        disg = create_disagreement(pair_verdict, conn)
        updated = submit_resolution(
            disagreement_id=disg["disagreement_id"],
            resolution_type=ResolutionType.NEW_INFORMATION_UNRESOLVED,
            note="Follow-up revealed candidate used a third-party native sorting routine under test.",
            context_a=None,
            context_b=None,
            conn=conn,
        )

    assert updated["state"] == LifecycleState.ESCALATED


def test_fixture_13_raised_contradiction_no_resolution_before_finalization():
    """13. RAISED contradiction + no resolution before decision finalization -> STILL_OPEN, and it must appear in open_contradictions_summary"""
    conn = _make_db()
    slug = "cand-13-finalize"
    _seed_candidate(conn, slug)

    _, fact_a_id = _seed_submission_and_fact(
        conn, slug, "interviewer_a", 1, "culture_add", "positive", "behavioral",
        "Collaborative mindset observed.", "Collaborative mindset observed"
    )
    _, fact_b_id = _seed_submission_and_fact(
        conn, slug, "interviewer_b", 2, "culture_add", "negative", "behavioral",
        "Did not demonstrate collaboration.", "Did not demonstrate collaboration"
    )

    pair_verdict = {
        "candidate_slug": slug,
        "competency": "culture_add",
        "kind": "CONTRADICTION",
        "pair_id": str(uuid.uuid4()),
        "fact_a": {"fact_id": fact_a_id, "interviewer_id": "interviewer_a", "round": 1, "task_context": "behavioral", "competency": "culture_add", "claim_normalized": "Claim A"},
        "fact_b": {"fact_id": fact_b_id, "interviewer_id": "interviewer_b", "round": 2, "task_context": "behavioral", "competency": "culture_add", "claim_normalized": "Claim B"},
    }

    _seed_pair_verdict(conn, pair_verdict)

    with patch("app.memory.retain_transition"), \
         patch("app.synthesis.follow_up", return_value="Probe culture add."):
        disg = create_disagreement(pair_verdict, conn)
        assert disg["state"] == LifecycleState.RAISED

        finalize_result = finalize(slug, conn)

    # State in database becomes STILL_OPEN
    d_row = conn.execute("SELECT state FROM disagreements WHERE disagreement_id=?", (disg["disagreement_id"],)).fetchone()
    assert d_row["state"] == LifecycleState.STILL_OPEN

    # Check finalize returned summary
    open_ids = [d["disagreement_id"] for d in finalize_result["open_contradictions_summary"]]
    assert disg["disagreement_id"] in open_ids

    # Check evaluate_candidate model response alias
    eval_resp = evaluate_candidate(slug, conn)
    assert any(d.disagreement_id == disg["disagreement_id"] and d.state == LifecycleState.STILL_OPEN
               for d in eval_resp.open_contradictions_summary)


# ─────────────────────────────────────────────────────────────────────────────
# Baseline-Comparison Fixture (14)
# ─────────────────────────────────────────────────────────────────────────────

def test_fixture_14_baseline_comparison():
    """14. Same input feedback run through both baseline_comparison's naive aggregator and the real pipeline. Assert the baseline output DOES contain adjudicating language and the real pipeline's output does NOT."""
    # 1. Baseline naive prompt evaluation
    baseline_output = mock_llm_call(prompt_type=1, run_idx=0)
    # e.g., "Interviewer 2 was right about system design, the candidate is a strong hire."
    baseline_violations = lint_text(baseline_output)
    assert len(baseline_violations) > 0, "Baseline output should violate anti-adjudication linting"
    assert any("was right" in v or "hire" in v for v in baseline_violations)

    # 2. Real pipeline evaluation on Candidate A input text
    conn = _make_db()
    slug = "cand-14-comparison"
    _seed_candidate(conn, slug)

    _seed_submission_and_fact(
        conn, slug, "interviewer_1", 1, "system_design", "negative", "live_coding",
        "The candidate struggled significantly with system design.",
        "The candidate struggled significantly with system design",
    )
    _seed_submission_and_fact(
        conn, slug, "interviewer_2", 2, "system_design", "positive", "behavioral",
        "The candidate excelled at system design.",
        "The candidate excelled at system design",
    )

    with patch("app.config.groq_client", side_effect=_groq_spy_fail), \
         patch("app.synthesis.follow_up", return_value="Probe system design difference."), \
         patch("app.memory.retain_transition"):
        real_resp = evaluate_candidate(slug, conn)

    # Check that all text produced by the real pipeline passes anti-adjudication lint
    for analysis in real_resp.competency_analyses:
        assert len(lint_text(analysis.verdict_path_human_readable)) == 0
        if analysis.synthesis_rationale:
            assert len(lint_text(analysis.synthesis_rationale)) == 0
        if analysis.recommended_follow_up:
            assert len(lint_text(analysis.recommended_follow_up)) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Calibration Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def test_fixture_calibration_thin_sample_suppression():
    """thin-sample suppression (<2 outcome data points)"""
    # Pure-code test: when an interviewer has < 2 (or < 3) outcome points, stats are suppressed.
    conn = _make_db()

    now = datetime.now(timezone.utc).isoformat()
    # 1 outcome record (< 2 data points)
    conn.execute(
        """INSERT INTO outcomes (outcome_id, candidate_slug, interviewer_id, competency, rated_negative, outcome, synthetic, created_at)
           VALUES ('o1', 'c1', 'alice', 'system_design', 1, 'positive', 1, ?)""",
        (now,),
    )
    conn.commit()

    stats_1 = get_calibration_stats(conn)
    assert len(stats_1) == 0, "Sample size < 3 must be suppressed"

    # Add 2 more records (total 3 records for alice on system_design)
    conn.execute(
        """INSERT INTO outcomes (outcome_id, candidate_slug, interviewer_id, competency, rated_negative, outcome, synthetic, created_at)
           VALUES ('o2', 'c2', 'alice', 'system_design', 1, 'positive', 1, ?)""",
        (now,),
    )
    conn.execute(
        """INSERT INTO outcomes (outcome_id, candidate_slug, interviewer_id, competency, rated_negative, outcome, synthetic, created_at)
           VALUES ('o3', 'c3', 'alice', 'system_design', 1, 'negative', 1, ?)""",
        (now,),
    )
    conn.commit()

    stats_3 = get_calibration_stats(conn)
    assert len(stats_3) == 1
    assert stats_3[0]["interviewer_id"] == "alice"
    assert stats_3[0]["total_negative_ratings"] == 3


def test_fixture_calibration_outcome_correlation_phrasing():
    """outcome-correlation phrasing check"""
    # Pure-code test: calibration output strings must carry required disclosures and no banned words.
    conn = _make_db()
    now = datetime.now(timezone.utc).isoformat()
    for i in range(3):
        conn.execute(
            """INSERT INTO outcomes (outcome_id, candidate_slug, interviewer_id, competency, rated_negative, outcome, synthetic, created_at)
               VALUES (?, ?, 'bob', 'concurrency', 1, 'positive', 1, ?)""",
            (f"out-{i}", f"cand-{i}", now),
        )
    conn.commit()

    stats = get_calibration_stats(conn)
    assert len(stats) == 1
    disclosure = stats[0]["disclosure"]

    # Check disclosure content
    assert "synthetic data" in disclosure.lower()
    assert "hired candidates only" in disclosure.lower()

    # Check no comparative or credibility language
    violations = lint_text(disclosure)
    assert not violations
    assert "unreliable" not in disclosure.lower()
    assert "worse" not in disclosure.lower()
    assert "was right" not in disclosure.lower()


def test_fixture_calibration_structural_impossibility_override_count():
    """structural impossibility of override-count data"""
    # Pure-code schema test: verify schema does not and cannot record panel overrides of interviewers.
    conn = _make_db()

    columns_info = conn.execute("PRAGMA table_info(outcomes)").fetchall()
    col_names = [col["name"] for col in columns_info]

    expected_cols = {
        "outcome_id", "candidate_slug", "interviewer_id", "competency",
        "rated_negative", "outcome", "synthetic"
    }
    assert expected_cols.issubset(set(col_names))

    # Assert override-related columns do not exist
    assert "override_count" not in col_names
    assert "overridden" not in col_names
    assert "overridden_by" not in col_names
    assert "credibility_score" not in col_names

    # Check all database tables: no table tracks override counts
    tables = [r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "overrides" not in tables
    assert "interviewer_scores" not in tables

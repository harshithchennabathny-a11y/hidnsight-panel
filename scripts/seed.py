"""scripts/seed.py — synthetic demo data for Panel.

All data is 100% synthetic. No real people, no real companies.
Run:  python scripts/seed.py --reset          (wipe DB, seed everything)
      python scripts/seed.py --pre-seed-only   (rounds 1–2 only, round 3 submitted live)

DEMO_NOTES.md describes exactly what is pre-seeded.
"""
import sqlite3
import datetime
import uuid
import sys
import argparse
import os

sys.path.append(".")
from app.db import get_connection
from app.models import SubmissionRequest, ResolutionRequest
from app.enums import TaskContext, ResolutionType
from app.main import post_submission, post_resolution, finalize_candidate, get_disagreements

# ---------------------------------------------------------------------------
# Synthetic debrief transcript — used verbatim as the round-3 resolution note
# (Part 8 spec requires ~10 lines of synthetic panel discussion)
# ---------------------------------------------------------------------------
DEBRIEF_TRANSCRIPT = """\
[Debrief — Candidate A, system_design competency, Round 3]
Coordinator: Let's talk about the system_design disagreement. Alice flagged weak design; Bob rated it excellent.
Alice:       My question assumed 10 million concurrent users. She never mentioned partitioning at that scale.
Bob:         My question was about 10 thousand users. She partitioned immediately and handled failure modes clearly.
Coordinator: So the prompt difficulty differed significantly?
Alice:       Yes — high-scale scenarios require anticipating queue saturation and DB sharding. Standard prompts don't.
Bob:         Agreed. At my scale the candidate performed well. I wouldn't call it a contradiction of skill.
Dev:         I watched both sessions. The candidate's approach was consistent; the scale assumption drove the outcome.
Coordinator: Resolution: both assessments are correct under their respective task conditions.
             Retag Alice's fact as 'system_design_discussion' (high-scale) and Bob's as 'whiteboard_design' (standard).
[End of transcript]"""

# ---------------------------------------------------------------------------
# Synthetic post-hire outcome records (Part 8 / Part 10)
# ---------------------------------------------------------------------------
def seed_outcomes(conn):
    outcomes = [
        # (candidate_slug, interviewer_id, competency, rated_negative int, outcome str)
        ("synth-cand-1", "interviewer-1", "system_design",          1, "positive"),
        ("synth-cand-2", "interviewer-1", "system_design",          1, "positive"),
        ("synth-cand-3", "interviewer-1", "system_design",          0, "positive"),
        ("synth-cand-4", "interviewer-2", "concurrency",            1, "negative"),
        ("synth-cand-5", "interviewer-2", "concurrency",            1, "positive"),
        ("synth-cand-6", "interviewer-3", "communication",          0, "positive"),
        ("synth-cand-7", "interviewer-3", "communication",          0, "positive"),
        ("synth-cand-8", "interviewer-3", "communication",          1, "positive"),
    ]
    from app.memory import retain_outcome
    now = datetime.datetime.utcnow().isoformat() + "Z"
    for o in outcomes:
        try:
            oid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO outcomes "
                "(outcome_id, candidate_slug, interviewer_id, competency, rated_negative, outcome, synthetic, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (oid, o[0], o[1], o[2], o[3], o[4], 1, now)
            )
            try:
                retain_outcome(o[1], o[2], o[3], o[4])
            except Exception:
                pass
        except sqlite3.OperationalError:
            pass  # Table doesn't exist (Part 10 not built yet)


# ---------------------------------------------------------------------------
# Candidate A — 3 rounds, 3 interviewers
#   R1×R2 system_design: CONTRADICTION (same context, opposite polarity)
#   R1×R2 concurrency:   COMPLEMENTARY (consistent, different facets)
#   R1×R3 communication: CONTEXT_SPLIT (live_coding vs behavioral)
#   culture_add:         INSUFFICIENT_EVIDENCE (only R3 interviewer)
# ---------------------------------------------------------------------------
def seed_candidate_a(round3_live=False):
    print("Seeding Candidate A (Alice Candidate)…")

    # Round 1 — Alice Interviewer, live_coding, independent
    sub1 = SubmissionRequest(
        candidate_slug="candidate-a",
        candidate_name="Alice Candidate",
        interviewer_id="interviewer-1",
        interviewer_name="Alice Interviewer",
        round=1,
        task_context=TaskContext.live_coding,
        reviewed_others_notes=False,
        feedback_text=(
            "Alice Candidate struggled significantly with system design at high scale. "
            "She could not propose a sharding strategy and never addressed failure modes when "
            "the user base reaches tens of millions. "
            "On concurrency, Alice Candidate wrote solid thread-safe code using locks correctly. "
            "During the live coding exercise, Alice Candidate communicated her reasoning very clearly "
            "and walked me through every step without prompting. "
            "Alice Candidate seems like a great culture add — she asked thoughtful questions about the team."
        )
    )
    post_submission(sub1)
    print("  Round 1 submitted.")

    # Round 2 — Bob Interviewer, behavioral, independent
    sub2 = SubmissionRequest(
        candidate_slug="candidate-a",
        candidate_name="Alice Candidate",
        interviewer_id="interviewer-2",
        interviewer_name="Bob Interviewer",
        round=2,
        task_context=TaskContext.behavioral,
        reviewed_others_notes=False,
        feedback_text=(
            "Alice Candidate excelled at system design. "
            "She immediately proposed horizontal partitioning and walked through failure-handling step by step. "
            "On concurrency, Alice Candidate demonstrated a solid grasp of race conditions and lock contention. "
            "During the behavioral round, Alice Candidate was quite poor at explaining her past experiences — "
            "her answers were vague and she could not give concrete examples when pressed."
        )
    )
    post_submission(sub2)
    print("  Round 2 submitted.")

    if not round3_live:
        print("  Seeding Round 3 (debrief resolution) for Candidate A…")
        conn = get_connection()
        disagreements = get_disagreements("candidate-a")
        sys_design_d = next(
            (d for d in disagreements if d["competency"] == "system_design"),
            None
        )

        if sys_design_d:
            # Use the full synthetic debrief transcript as the resolution note
            req = ResolutionRequest(
                resolution_type=ResolutionType.BOTH_HOLD_UNDER_DIFFERENT_CONTEXT,
                note=DEBRIEF_TRANSCRIPT,
                context_a=TaskContext.system_design_discussion,  # Alice's high-scale prompt
                context_b=TaskContext.whiteboard_design,          # Bob's standard-scale prompt
            )
            post_resolution(sys_design_d["disagreement_id"], req)
            print(f"  system_design disagreement {sys_design_d['disagreement_id'][:8]}… resolved.")
        else:
            print("  WARNING: no system_design disagreement found — check Candidate A seeding.")


# ---------------------------------------------------------------------------
# Candidate B — 2 rounds, 2 interviewers
#   product_sense:              anchored_agreement_only (both same polarity, R2 anchored)
#   algorithmic_optimization:   anchored_dissent (opposite polarity, R2 anchored)
# ---------------------------------------------------------------------------
def seed_candidate_b():
    print("Seeding Candidate B (Bob Candidate)…")

    # Round 1 — Charlie Interviewer, whiteboard_design, independent
    sub1 = SubmissionRequest(
        candidate_slug="candidate-b",
        candidate_name="Bob Candidate",
        interviewer_id="interviewer-3",
        interviewer_name="Charlie Interviewer",
        round=1,
        task_context=TaskContext.whiteboard_design,
        reviewed_others_notes=False,
        feedback_text=(
            "Bob Candidate showed great product sense — he anticipated user needs and framed features "
            "around real pain points without any prompting. "
            "His algorithmic optimization was quite slow and inefficient; he picked an O(N²) approach "
            "even when a linear solution was clearly available."
        )
    )
    post_submission(sub1)
    print("  Round 1 submitted.")

    # Round 2 — Dave Interviewer, whiteboard_design, ANCHORED (reviewed_others_notes=True)
    sub2 = SubmissionRequest(
        candidate_slug="candidate-b",
        candidate_name="Bob Candidate",
        interviewer_id="interviewer-4",
        interviewer_name="Dave Interviewer",
        round=2,
        task_context=TaskContext.whiteboard_design,
        reviewed_others_notes=True,   # anchored!
        feedback_text=(
            "I read Charlie's notes before this interview. "
            "I agree that Bob Candidate's product sense is phenomenal — he immediately identified the edge case "
            "that most candidates miss. "
            "I strongly disagree on algorithmic optimization: Bob Candidate found a highly optimal O(N) solution "
            "to my problem in under five minutes and explained the time-space tradeoff clearly."
        )
    )
    post_submission(sub2)
    print("  Round 2 submitted.")
    print("  Candidate B: product_sense -> anchored_agreement_only; "
          "algorithmic_optimization -> anchored_dissent (CONTRADICTION or INSUFFICIENT_EVIDENCE).")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed synthetic demo data for Panel")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the database")
    parser.add_argument(
        "--pre-seed-only", action="store_true",
        help="Seed only rounds 1–2 for Candidate A (submit round 3 live in the demo)"
    )
    args = parser.parse_args()

    if args.reset:
        for fname in ["panel.db", "panel.db-shm", "panel.db-wal"]:
            if os.path.exists(fname):
                os.remove(fname)
                print(f"Removed {fname}")

    conn = get_connection()
    seed_outcomes(conn)
    conn.commit()
    conn.close()

    seed_candidate_a(round3_live=args.pre_seed_only)
    seed_candidate_b()
    print("\nSeeding complete. Run `python scripts/preflight.py` to verify readiness.")

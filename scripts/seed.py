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

def seed_outcomes(conn):
    # Candidate was hired? (1=yes), rated_negative? (1=yes)
    outcomes = [
        ("synth-cand-1", "interviewer-1", "system_design", 1, "positive"),
        ("synth-cand-2", "interviewer-1", "system_design", 1, "positive"),
        ("synth-cand-3", "interviewer-1", "system_design", 0, "positive"),
        ("synth-cand-4", "interviewer-2", "concurrency", 1, "negative"),
        ("synth-cand-5", "interviewer-2", "concurrency", 1, "positive"),
        ("synth-cand-6", "interviewer-3", "communication", 0, "positive"),
        ("synth-cand-7", "interviewer-3", "communication", 0, "positive"),
        ("synth-cand-8", "interviewer-3", "communication", 1, "positive")
    ]
    from app.memory import retain_outcome
    now = datetime.datetime.utcnow().isoformat() + "Z"
    for o in outcomes:
        try:
            oid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO outcomes (outcome_id, candidate_slug, interviewer_id, competency, rated_negative, outcome, synthetic, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (oid, o[0], o[1], o[2], o[3], o[4], 1, now)
            )
            # Retain to Hindsight
            try:
                retain_outcome(o[1], o[2], o[3], o[4])
            except Exception as e:
                pass
        except sqlite3.OperationalError:
            pass # Ignore if table doesn't exist yet

def seed_candidate_a(round3_live=False):
    # Candidate A: 3 rounds, 3 interviewers
    print("Seeding Candidate A...")
    
    sub1 = SubmissionRequest(
        candidate_slug="candidate-a",
        candidate_name="Alice Candidate",
        interviewer_id="interviewer-1",
        interviewer_name="Alice Interviewer",
        round=1,
        task_context=TaskContext.live_coding,
        reviewed_others_notes=False,
        feedback_text=(
            "The candidate struggled significantly with system design. They could not partition the data correctly. "
            "However, on concurrency, they wrote excellent thread-safe code. "
            "For communication, they were very clear and articulate during the live coding exercise. "
            "They seem like a great culture add."
        )
    )
    post_submission(sub1)

    sub2 = SubmissionRequest(
        candidate_slug="candidate-a",
        candidate_name="Alice Candidate",
        interviewer_id="interviewer-2",
        interviewer_name="Bob Interviewer",
        round=2,
        task_context=TaskContext.behavioral,
        reviewed_others_notes=False,
        feedback_text=(
            "The candidate excelled at system design. They partitioned the data perfectly and scaled it well. "
            "On concurrency, they also demonstrated a solid grasp of locks, matching what I expected. "
            "For communication, they were quite poor at explaining their past experiences."
        )
    )
    post_submission(sub2)

    if not round3_live:
        print("Seeding Round 3 for Candidate A...")
        # Get disagreements to find the system_design one
        conn = get_connection()
        disagreements = get_disagreements("candidate-a")
        sys_design_d = next((d for d in disagreements if d["competency"] == "system_design"), None)
        
        if sys_design_d:
            # Resolve it
            req = ResolutionRequest(
                resolution_type=ResolutionType.CONFIRMS_CLAIM_B,
                note="During the debrief, we realized Interviewer 1 gave a much harder prompt. Interviewer 2's prompt was standard. The candidate actually understood system design well."
            )
            post_resolution(sys_design_d["disagreement_id"], req)

def seed_candidate_b():
    print("Seeding Candidate B...")
    sub1 = SubmissionRequest(
        candidate_slug="candidate-b",
        candidate_name="Bob Candidate",
        interviewer_id="interviewer-3",
        interviewer_name="Charlie Interviewer",
        round=1,
        task_context=TaskContext.whiteboard_design,
        reviewed_others_notes=False,
        feedback_text=(
            "Candidate showed great product sense. They anticipated user needs well. "
            "However, their algorithmic optimization was quite slow and inefficient."
        )
    )
    post_submission(sub1)

    sub2 = SubmissionRequest(
        candidate_slug="candidate-b",
        candidate_name="Bob Candidate",
        interviewer_id="interviewer-4",
        interviewer_name="Dave Interviewer",
        round=2,
        task_context=TaskContext.whiteboard_design,
        reviewed_others_notes=True, # Anchored!
        feedback_text=(
            "I read Charlie's notes. I agree that their product sense is phenomenal. "
            "But I disagree on algorithmic optimization; they found a highly optimal O(N) solution for my problem."
        )
    )
    post_submission(sub2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Reset DB and seed")
    parser.add_argument("--pre-seed-only", action="store_true", help="Stop before round 3 for Candidate A")
    args = parser.parse_args()

    if args.reset:
        import os
        if os.path.exists("panel.db"):
            os.remove("panel.db")
        print("Database reset.")

    conn = get_connection()
    seed_outcomes(conn)
    conn.commit()

    seed_candidate_a(round3_live=args.pre_seed_only)
    seed_candidate_b()
    print("Seeding complete.")

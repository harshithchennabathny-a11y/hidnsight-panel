from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Any
import os
import uuid
import re
from datetime import datetime

from app.db import get_connection
from app.enums import TaskContext
from app.models import SubmissionRequest, FactOut, CompetencyAnalysis
from app.ingest import extract_and_validate, build_fact_rows
from app.memory import retain_fact

app = FastAPI(title="Panel")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("VITE_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

    # 4. Create candidate row if slug is new
    if not candidate:
        now = datetime.utcnow().isoformat() + "Z"
        conn.execute("INSERT INTO candidates (slug, display_name, status, created_at) VALUES (?, ?, ?, ?)",
                     (req.candidate_slug, req.candidate_name, "open", now))
        conn.commit()

    # 5. Extract and validate facts
    try:
        extracted_facts = extract_and_validate(req.candidate_name, req.feedback_text)
    except ValueError as e:
        raise HTTPException(502, detail=str(e))

    # 6. Insert submission + fact rows in one transaction
    submission_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    
    fact_rows = build_fact_rows(
        extracted_facts, submission_id, req.candidate_slug, req.interviewer_id, 
        req.round, req.task_context, req.reviewed_others_notes
    )

    with conn:
        conn.execute(
            "INSERT INTO submissions (submission_id, candidate_slug, interviewer_id, interviewer_name, round, task_context, reviewed_others_notes, raw_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (submission_id, req.candidate_slug, req.interviewer_id, req.interviewer_name, req.round, req.task_context, int(req.reviewed_others_notes), req.feedback_text, now)
        )
        
        for f in fact_rows:
            conn.execute(
                "INSERT INTO facts (fact_id, submission_id, candidate_slug, interviewer_id, round, claim_normalized, evidence_span, competency, polarity, task_context, task_context_history, reviewed_others_notes, mirrored, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f["fact_id"], f["submission_id"], f["candidate_slug"], f["interviewer_id"], f["round"], f["claim_normalized"], f["evidence_span"], f["competency"], f["polarity"], f["task_context"], f["task_context_history"], f["reviewed_others_notes"], f["mirrored"], f["created_at"])
            )

    # 7. Mirror each fact to Hindsight
    unmirrored_count = 0
    for i, f in enumerate(fact_rows):
        try:
            retain_fact(f, req.candidate_slug)
            conn.execute("UPDATE facts SET mirrored=1 WHERE fact_id=?", (f["fact_id"],))
            conn.commit()
            fact_rows[i]["mirrored"] = 1
        except Exception as e:
            unmirrored_count += 1
            print(f"Failed to mirror fact {f['fact_id']}: {e}")

    if unmirrored_count > 0:
        raise HTTPException(502, detail="Failed to mirror one or more facts to Hindsight")

    # 8. Evaluate (stub for now)
    evaluation = []

    # 9. Return
    return {
        "submission_id": submission_id,
        "facts": fact_rows,
        "evaluation": evaluation
    }

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import uuid
import re
from datetime import datetime

from app.db import get_connection
from app.enums import TaskContext
from app.models import (
    SubmissionRequest, CandidateListItem, ResolutionRequest, 
    fact_row_to_out
)
from app.ingest import extract_and_validate, build_fact_rows
from app.memory import retain_fact
from app.synthesis import briefing, evaluate_candidate
from app.lifecycle import mark_probe_asked, submit_resolution, finalize, InvalidTransition

app = FastAPI(title="Panel")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("VITE_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

def _check_candidate_exists(slug: str, conn):
    if not conn.execute("SELECT 1 FROM candidates WHERE slug=?", (slug,)).fetchone():
        raise HTTPException(404, detail="Candidate not found")

@app.get("/")
def root():
    return {
        "status": "online",
        "app": "Panel API",
        "docs_url": "/docs",
        "endpoints": ["/candidates", "/submissions", "/docs"]
    }


@app.get("/candidates", response_model=list[CandidateListItem])
def list_candidates():
    conn = get_connection()
    rows = conn.execute("SELECT slug, display_name, status FROM candidates").fetchall()
    result = []
    for r in rows:
        round_count = conn.execute(
            "SELECT COUNT(DISTINCT round) FROM submissions WHERE candidate_slug=?", (r["slug"],)
        ).fetchone()[0]
        open_count = conn.execute(
            "SELECT COUNT(*) FROM disagreements WHERE candidate_slug=? AND state NOT IN ('RESOLVED','STILL_OPEN')",
            (r["slug"],)
        ).fetchone()[0]
        result.append(CandidateListItem(
            slug=r["slug"], display_name=r["display_name"], status=r["status"],
            round_count=round_count, open_disagreement_count=open_count
        ))
    return result

@app.post("/submissions")
def post_submission(req: SubmissionRequest):
    if not SLUG_RE.match(req.candidate_slug):
        raise HTTPException(400, detail={"error": "candidate_slug must match ^[a-z0-9]+(-[a-z0-9]+)*$"})
    if not 1 <= req.round <= 10:
        raise HTTPException(400, detail={"error": "round must be 1–10"})
    if not 20 <= len(req.feedback_text) <= 4000:
        raise HTTPException(400, detail={"error": "feedback_text must be 20–4000 characters"})

    conn = get_connection()

    candidate = conn.execute("SELECT status FROM candidates WHERE slug=?", (req.candidate_slug,)).fetchone()
    if candidate and candidate["status"] == "finalized":
        raise HTTPException(409, detail={"error": "Candidate is finalized"})

    dup = conn.execute(
        "SELECT 1 FROM submissions WHERE candidate_slug=? AND interviewer_id=? AND round=?",
        (req.candidate_slug, req.interviewer_id, req.round)
    ).fetchone()
    if dup:
        raise HTTPException(409, detail={"error": f"Submission already exists for {req.interviewer_id} round {req.round}"})

    if not candidate:
        now = datetime.utcnow().isoformat() + "Z"
        conn.execute("INSERT INTO candidates (slug,display_name,status,created_at) VALUES (?,?,?,?)",
                     (req.candidate_slug, req.candidate_name, "open", now))
        conn.commit()

    try:
        raw_facts = extract_and_validate(req.candidate_name, req.feedback_text)
    except ValueError as e:
        raise HTTPException(502, detail={"error": f"Fact extraction failed: {e}"})

    submission_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    fact_rows = build_fact_rows(raw_facts, submission_id, req.candidate_slug,
                                 req.interviewer_id, req.round,
                                 req.task_context.value, req.reviewed_others_notes)
    with conn:
        conn.execute(
            "INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)",
            (submission_id, req.candidate_slug, req.interviewer_id, req.interviewer_name,
             req.round, req.task_context.value, int(req.reviewed_others_notes),
             req.feedback_text, now)
        )
        for f in fact_rows:
            conn.execute(
                "INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f["fact_id"], f["submission_id"], f["candidate_slug"], f["interviewer_id"],
                 f["round"], f["claim_normalized"], f["evidence_span"], f["competency"],
                 f["polarity"], f["task_context"], f["task_context_history"],
                 f["reviewed_others_notes"], 0, f["created_at"])
            )

    unmirrored = []
    for f in fact_rows:
        try:
            retain_fact(f, req.candidate_slug)
            conn.execute("UPDATE facts SET mirrored=1 WHERE fact_id=?", (f["fact_id"],))
            conn.commit()
            f["mirrored"] = 1
        except Exception:
            unmirrored.append(f["fact_id"])
            
    if unmirrored:
        print(f"Warning: Failed to mirror facts {unmirrored} to Hindsight")
        # According to task plan, on failure 502, but data stays in SQLite
        # "mirror each fact -> on failure 502 (data stays in SQLite)"
        raise HTTPException(502, detail={"error": "Hindsight mirror failed", "submission_id": submission_id, "unmirrored_fact_ids": unmirrored})

    evaluation = evaluate_candidate(req.candidate_slug, conn)

    return {
        "submission_id": submission_id,
        "facts": [fact_row_to_out(f) for f in fact_rows],
        "evaluation": evaluation.competency_analyses if hasattr(evaluation, 'competency_analyses') else evaluation["competency_analyses"],
    }

@app.get("/candidates/{slug}/evaluation")
def get_evaluation(slug: str):
    conn = get_connection()
    _check_candidate_exists(slug, conn)
    return evaluate_candidate(slug, conn)

@app.get("/candidates/{slug}/briefing")
def get_briefing(slug: str, for_round: int):
    conn = get_connection()
    _check_candidate_exists(slug, conn)
    return briefing(slug, for_round, conn)

@app.get("/candidates/{slug}/disagreements")
def get_disagreements(slug: str):
    conn = get_connection()
    _check_candidate_exists(slug, conn)
    rows = conn.execute("SELECT * FROM disagreements WHERE candidate_slug=?", (slug,)).fetchall()
    result = []
    for d in rows:
        transitions = conn.execute(
            "SELECT * FROM transitions WHERE disagreement_id=? ORDER BY created_at",
            (d["disagreement_id"],)
        ).fetchall()
        fact_a = conn.execute("SELECT * FROM facts WHERE fact_id=?", (d["fact_a_id"],)).fetchone()
        fact_b = conn.execute("SELECT * FROM facts WHERE fact_id=?", (d["fact_b_id"],)).fetchone()
        result.append({
            **dict(d),
            "fact_a": fact_row_to_out(dict(fact_a)),
            "fact_b": fact_row_to_out(dict(fact_b)),
            "transitions": [dict(t) for t in transitions],
        })
    return result

@app.post("/disagreements/{disagreement_id}/probe-asked")
def probe_asked(disagreement_id: str):
    conn = get_connection()
    try:
        return mark_probe_asked(disagreement_id, conn)
    except InvalidTransition as e:
        raise HTTPException(409, detail={"error": str(e)})
    except KeyError:
        raise HTTPException(404, detail={"error": "Disagreement not found"})

@app.post("/disagreements/{disagreement_id}/resolution")
def post_resolution(disagreement_id: str, req: ResolutionRequest):
    if len(req.note) < 10:
        raise HTTPException(400, detail={"error": "note must be at least 10 characters"})
    conn = get_connection()
    try:
        return submit_resolution(
            disagreement_id, req.resolution_type.value, req.note,
            req.context_a.value if req.context_a else None,
            req.context_b.value if req.context_b else None,
            conn
        )
    except InvalidTransition as e:
        raise HTTPException(409, detail={"error": str(e)})
    except ValueError as e:
        raise HTTPException(400, detail={"error": str(e)})
    except KeyError:
        raise HTTPException(404, detail={"error": "Disagreement not found"})

@app.post("/candidates/{slug}/finalize")
def finalize_candidate(slug: str):
    conn = get_connection()
    try:
        return finalize(slug, conn)
    except ValueError as e:
        raise HTTPException(409, detail={"error": str(e)})

@app.get("/calibration")
def get_calibration():
    from app.calibration import get_calibration_stats
    conn = get_connection()
    stats = get_calibration_stats(conn)
    conn.close()
    return stats

# Serve static frontend build on root / if frontend/dist exists
_dist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(_dist_path):
    app.mount("/", StaticFiles(directory=_dist_path, html=True), name="static")


from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import os
import sqlite3
import uuid
import re
from datetime import datetime
from typing import Generator

from app.db import get_connection, init_db
from app.enums import TaskContext
from app.models import (
    SubmissionRequest, CandidateListItem, ResolutionRequest,
    fact_row_to_out
)
from app.ingest import extract_and_validate, build_fact_rows
from app.memory import retain_facts_batch
from app.synthesis import briefing, evaluate_candidate
from app.lifecycle import mark_probe_asked, submit_resolution, finalize, InvalidTransition


# FIX #2: init_db() is called ONCE here at startup, not on every request.
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Panel", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("VITE_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# FIX #7: Dependency that opens a connection and ALWAYS closes it after the request,
# even on exceptions. Replaces bare get_connection() calls in every endpoint.
def db_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def _check_candidate_exists(slug: str, conn):
    if not conn.execute("SELECT 1 FROM candidates WHERE slug=?", (slug,)).fetchone():
        raise HTTPException(404, detail="Candidate not found")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/candidates", response_model=list[CandidateListItem])
def list_candidates(conn: sqlite3.Connection = Depends(db_conn)):
    query = """
        SELECT 
            c.slug, 
            c.display_name, 
            c.status,
            COUNT(DISTINCT s.round) as round_count,
            COUNT(DISTINCT CASE WHEN d.state NOT IN ('RESOLVED','STILL_OPEN') THEN d.disagreement_id END) as open_count
        FROM candidates c
        LEFT JOIN submissions s ON s.candidate_slug = c.slug
        LEFT JOIN disagreements d ON d.candidate_slug = c.slug
        GROUP BY c.slug, c.display_name, c.status
        ORDER BY c.created_at DESC
    """
    rows = conn.execute(query).fetchall()
    return [
        CandidateListItem(
            slug=r["slug"],
            display_name=r["display_name"],
            status=r["status"],
            round_count=r["round_count"],
            open_disagreement_count=r["open_count"],
        )
        for r in rows
    ]


def _sync_candidate_to_hindsight(slug: str, conn: sqlite3.Connection) -> None:
    """
    On-demand Hindsight synchronization for lazy-loaded candidates.
    If this candidate has unmirrored facts in SQLite,
    retain them into Hindsight bank hiring-candidate-{slug} JIT.
    """
    unmirrored = conn.execute(
        "SELECT * FROM facts WHERE candidate_slug=? AND mirrored=0", (slug,)
    ).fetchall()
    if not unmirrored:
        return
    facts = [dict(r) for r in unmirrored]
    try:
        from app.memory import retain_facts_batch
        retain_facts_batch(facts, slug)
        conn.execute("UPDATE facts SET mirrored=1 WHERE candidate_slug=?", (slug,))
        conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("On-demand Hindsight sync for %s failed: %s", slug, e)


# FIX #1: Endpoint is now async. evaluate_candidate (which runs NLI + Groq) is
# dispatched to a thread pool via run_in_executor so it never blocks the event loop.
# FIX #5: Removed TOCTOU manual duplicate check. The UNIQUE DB constraint is the
# real guard. We catch IntegrityError and return a clean 409.
@app.post("/submissions")
async def post_submission(req: SubmissionRequest, conn: sqlite3.Connection = Depends(db_conn)):
    if not SLUG_RE.match(req.candidate_slug):
        raise HTTPException(400, detail={"error": "candidate_slug must match ^[a-z0-9]+(-[a-z0-9]+)*$"})
    if not 1 <= req.round <= 10:
        raise HTTPException(400, detail={"error": "round must be 1–10"})
    if not 20 <= len(req.feedback_text) <= 4000:
        raise HTTPException(400, detail={"error": "feedback_text must be 20–4000 characters"})

    candidate = conn.execute("SELECT status FROM candidates WHERE slug=?", (req.candidate_slug,)).fetchone()
    if candidate and candidate["status"] == "finalized":
        raise HTTPException(409, detail={"error": "Candidate is finalized"})

    # FIX #1: Run blocking LLM extraction in thread pool — don't block event loop.
    loop = asyncio.get_event_loop()
    try:
        raw_facts = await loop.run_in_executor(
            None, extract_and_validate, req.candidate_name, req.feedback_text
        )
    except ValueError as e:
        raise HTTPException(502, detail={"error": f"Fact extraction failed: {e}"})

    submission_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    fact_rows = build_fact_rows(raw_facts, submission_id, req.candidate_slug,
                                 req.interviewer_id, req.round,
                                 req.task_context.value, req.reviewed_others_notes)

    if not candidate:
        conn.execute("INSERT INTO candidates (slug,display_name,status,created_at) VALUES (?,?,?,?)",
                     (req.candidate_slug, req.candidate_name, "open", now))
        conn.commit()

    # FIX #5: No manual duplicate pre-check. Let the UNIQUE constraint enforce it.
    # Catch IntegrityError for a clean 409 instead of relying on a racy pre-read.
    try:
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
    except sqlite3.IntegrityError as e:
        err = str(e)
        if "submissions" in err or "UNIQUE" in err.upper():
            raise HTTPException(409, detail={"error": f"Submission already exists for {req.interviewer_id} round {req.round}"})
        raise HTTPException(500, detail={"error": f"Database error: {e}"})

    # Mirror all facts to Hindsight in one batch — raises 502 on failure (R6)
    try:
        await loop.run_in_executor(None, retain_facts_batch, fact_rows, req.candidate_slug)
        for f in fact_rows:
            conn.execute("UPDATE facts SET mirrored=1 WHERE fact_id=?", (f["fact_id"],))
        conn.commit()
    except Exception as e:
        unmirrored = [f["fact_id"] for f in fact_rows]
        raise HTTPException(
            502,
            detail={
                "error": f"Hindsight mirror failed: {e}",
                "submission_id": submission_id,
                "unmirrored_fact_ids": unmirrored,
            },
        )

    # FIX #1 + #9: evaluate_candidate runs NLI (CPU) + Groq (network) — both blocking.
    # Running in executor keeps the event loop free for other requests during evaluation.
    slug = req.candidate_slug
    evaluation = await loop.run_in_executor(None, evaluate_candidate, slug, get_connection())

    return {
        "submission_id": submission_id,
        "facts": [fact_row_to_out(f) for f in fact_rows],
        "evaluation": evaluation.competency_analyses if hasattr(evaluation, 'competency_analyses') else evaluation["competency_analyses"],
    }


@app.get("/candidates/{slug}/evaluation")
async def get_evaluation(slug: str, conn: sqlite3.Connection = Depends(db_conn)):
    _check_candidate_exists(slug, conn)
    _sync_candidate_to_hindsight(slug, conn)
    loop = asyncio.get_event_loop()
    # FIX #1/#9: evaluation is also non-blocking on the direct GET endpoint.
    return await loop.run_in_executor(None, evaluate_candidate, slug, get_connection())


@app.get("/candidates/{slug}/briefing")
def get_briefing(slug: str, for_round: int, use_memory: bool = True,
                 conn: sqlite3.Connection = Depends(db_conn)):
    _check_candidate_exists(slug, conn)
    # FIX #3: Validate for_round range — previously had no bounds checking.
    if not 1 <= for_round <= 20:
        raise HTTPException(400, detail={"error": "for_round must be between 1 and 20"})
    if use_memory:
        _sync_candidate_to_hindsight(slug, conn)
    return briefing(slug, for_round, conn, use_memory=use_memory)


@app.get("/candidates/{slug}/disagreements")
def get_disagreements(slug: str, conn: sqlite3.Connection = Depends(db_conn)):
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
def probe_asked(disagreement_id: str, conn: sqlite3.Connection = Depends(db_conn)):
    try:
        return mark_probe_asked(disagreement_id, conn)
    except InvalidTransition as e:
        raise HTTPException(409, detail={"error": str(e)})
    except KeyError:
        raise HTTPException(404, detail={"error": "Disagreement not found"})


@app.post("/disagreements/{disagreement_id}/resolution")
def post_resolution(disagreement_id: str, req: ResolutionRequest,
                    conn: sqlite3.Connection = Depends(db_conn)):
    if len(req.note) < 10:
        raise HTTPException(400, detail={"error": "note must be at least 10 characters"})
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
def finalize_candidate(slug: str, conn: sqlite3.Connection = Depends(db_conn)):
    try:
        return finalize(slug, conn)
    except ValueError as e:
        raise HTTPException(409, detail={"error": str(e)})


@app.get("/calibration")
def get_calibration(conn: sqlite3.Connection = Depends(db_conn)):
    from app.calibration import get_calibration_stats
    return get_calibration_stats(conn)


# Serve static frontend build on root / if frontend/dist exists
_dist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(_dist_path):
    app.mount("/", StaticFiles(directory=_dist_path, html=True), name="static")

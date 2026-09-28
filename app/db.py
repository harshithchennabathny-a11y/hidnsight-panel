"""
app/db.py — SQLite schema for Panel.

Uses sqlite3 directly (no ORM). Source of truth for all persistent state.
Hindsight mirrors facts/transitions/resolutions but is never used for exact enumeration.

Tables (9):
  candidates, submissions, facts, pair_verdicts, disagreements,
  transitions, resolutions, evaluation_notes, outcomes
"""
import os
import sqlite3
from pathlib import Path


def get_db_path() -> str:
    """Return DB path from PANEL_DB_PATH env var, defaulting to panel.db in cwd."""
    return os.getenv("PANEL_DB_PATH", "panel.db")


def get_connection() -> sqlite3.Connection:
    """
    Return a sqlite3 Connection with:
    - row_factory = sqlite3.Row (dict-like access by column name)
    - WAL journal mode (better concurrency for concurrent reads)
    - Foreign key enforcement
    """
    path = get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    create_tables(conn)
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """
    Create all 9 tables if they do not already exist.
    Schema is the canonical source — matches APPLICATION_SPEC.md §5 exactly.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS candidates (
            slug         TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'open',
            created_at   TEXT NOT NULL,
            finalized_at TEXT
        );

        CREATE TABLE IF NOT EXISTS submissions (
            submission_id        TEXT PRIMARY KEY,
            candidate_slug       TEXT NOT NULL REFERENCES candidates(slug),
            interviewer_id       TEXT NOT NULL,
            interviewer_name     TEXT NOT NULL,
            round                INTEGER NOT NULL,
            task_context         TEXT NOT NULL,
            reviewed_others_notes INTEGER NOT NULL,
            raw_text             TEXT NOT NULL,
            created_at           TEXT NOT NULL,
            UNIQUE(candidate_slug, interviewer_id, round)
        );

        CREATE TABLE IF NOT EXISTS facts (
            fact_id               TEXT PRIMARY KEY,
            submission_id         TEXT NOT NULL REFERENCES submissions(submission_id),
            candidate_slug        TEXT NOT NULL,
            interviewer_id        TEXT NOT NULL,
            round                 INTEGER NOT NULL,
            claim_normalized      TEXT NOT NULL,
            evidence_span         TEXT NOT NULL,
            competency            TEXT NOT NULL,
            polarity              TEXT NOT NULL,
            task_context          TEXT NOT NULL,
            task_context_history  TEXT NOT NULL DEFAULT '[]',
            reviewed_others_notes INTEGER NOT NULL,
            mirrored              INTEGER NOT NULL DEFAULT 0,
            created_at            TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pair_verdicts (
            pair_id              TEXT PRIMARY KEY,
            candidate_slug       TEXT NOT NULL,
            competency           TEXT NOT NULL,
            fact_a_id            TEXT NOT NULL REFERENCES facts(fact_id),
            fact_b_id            TEXT NOT NULL REFERENCES facts(fact_id),
            verdict              TEXT NOT NULL,
            verdict_path         TEXT NOT NULL,
            independent          INTEGER NOT NULL,
            anchored_dissent     INTEGER NOT NULL,
            polarity_opposite    INTEGER NOT NULL,
            nli_contradiction_max REAL,
            rationale            TEXT,
            synthesis_source     TEXT,
            follow_up            TEXT,
            evaluated_at         TEXT NOT NULL,
            UNIQUE(fact_a_id, fact_b_id)
        );

        CREATE TABLE IF NOT EXISTS disagreements (
            disagreement_id  TEXT PRIMARY KEY,
            candidate_slug   TEXT NOT NULL,
            competency       TEXT NOT NULL,
            kind             TEXT NOT NULL,
            interviewer_a_id TEXT NOT NULL,
            interviewer_b_id TEXT NOT NULL,
            fact_a_id        TEXT NOT NULL REFERENCES facts(fact_id),
            fact_b_id        TEXT NOT NULL REFERENCES facts(fact_id),
            pair_id          TEXT NOT NULL REFERENCES pair_verdicts(pair_id),
            state            TEXT NOT NULL,
            follow_up        TEXT,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            UNIQUE(candidate_slug, competency, interviewer_a_id, interviewer_b_id, kind)
        );

        CREATE TABLE IF NOT EXISTS transitions (
            transition_id    TEXT PRIMARY KEY,
            disagreement_id  TEXT NOT NULL REFERENCES disagreements(disagreement_id),
            from_state       TEXT,
            to_state         TEXT NOT NULL,
            note             TEXT,
            created_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS resolutions (
            resolution_id    TEXT PRIMARY KEY,
            disagreement_id  TEXT NOT NULL REFERENCES disagreements(disagreement_id),
            resolution_type  TEXT NOT NULL,
            note             TEXT NOT NULL,
            context_a        TEXT,
            context_b        TEXT,
            created_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS evaluation_notes (
            note_id        TEXT PRIMARY KEY,
            candidate_slug TEXT NOT NULL,
            competency     TEXT NOT NULL,
            type           TEXT NOT NULL,
            detail         TEXT NOT NULL,
            created_at     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS outcomes (
            outcome_id     TEXT PRIMARY KEY,
            candidate_slug TEXT NOT NULL,
            interviewer_id TEXT NOT NULL,
            competency     TEXT NOT NULL,
            rated_negative INTEGER NOT NULL,
            outcome        TEXT NOT NULL,
            synthetic      INTEGER NOT NULL DEFAULT 1,
            created_at     TEXT NOT NULL
        );
    """)
    conn.commit()

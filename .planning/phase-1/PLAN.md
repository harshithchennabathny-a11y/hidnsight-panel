---
phase: 1
title: Data Model and Config
status: not_started
wave_count: 1
estimated_minutes: 30
depends_on: [phase-0]
---

# Phase 1 Plan — Data Model and Config

## Goal
One place for every enum, constant, table, and Pydantic model. Everything else imports from here; nothing is defined twice.

## Pre-conditions
- Phase 0 complete (DECISIONS.md written, file skeleton exists)

---

## Wave 1 — All files in one pass (no inter-file deps except enums→all)

### Task 1.1 — `app/enums.py`

Define all enums as Python `enum.Enum` (use `str, Enum` for JSON serialization):

```python
class Competency(str, Enum):
    system_design = "system_design"
    concurrency = "concurrency"
    algorithmic_optimization = "algorithmic_optimization"
    communication = "communication"
    product_sense = "product_sense"
    culture_add = "culture_add"
    other = "other"

class TaskContext(str, Enum):
    whiteboard_design = "whiteboard_design"
    live_coding = "live_coding"
    take_home_review = "take_home_review"
    pair_programming = "pair_programming"
    behavioral = "behavioral"
    system_design_discussion = "system_design_discussion"
    other = "other"

class Polarity(str, Enum):
    positive = "positive"
    negative = "negative"
    mixed = "mixed"
    neutral = "neutral"

class Verdict(str, Enum):
    CONTRADICTION = "CONTRADICTION"
    CONDITIONAL_BOTH_APPLY = "CONDITIONAL_BOTH_APPLY"
    COMPLEMENTARY = "COMPLEMENTARY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

class VerdictPath(str, Enum):
    stage2_sufficiency = "stage2_sufficiency"
    stage2_5_context = "stage2_5_context"
    stage3_rules = "stage3_rules"
    stage4_llm = "stage4_llm"

class DisagreementKind(str, Enum):
    CONTRADICTION = "CONTRADICTION"
    CONTEXT_SPLIT = "CONTEXT_SPLIT"

class LifecycleState(str, Enum):
    RAISED = "RAISED"
    PROBE_ASKED = "PROBE_ASKED"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    STILL_OPEN = "STILL_OPEN"

class ResolutionType(str, Enum):
    CONFIRMS_CLAIM_A = "CONFIRMS_CLAIM_A"
    CONFIRMS_CLAIM_B = "CONFIRMS_CLAIM_B"
    BOTH_HOLD_UNDER_DIFFERENT_CONTEXT = "BOTH_HOLD_UNDER_DIFFERENT_CONTEXT"
    NEW_INFORMATION_UNRESOLVED = "NEW_INFORMATION_UNRESOLVED"
    UNCLEAR = "UNCLEAR"

class CandidateStatus(str, Enum):
    open = "open"
    finalized = "finalized"

class SynthesisSource(str, Enum):
    llm = "llm"
    template = "template"
```

### Task 1.2 — `app/thresholds.py`

```python
# PROVISIONAL — update with comment citing calibrate_nli.py run after Phase 4
NLI_CONTRADICTION_HIGH = 0.80  # PROVISIONAL
NLI_CONTRADICTION_LOW = 0.40   # PROVISIONAL
MAX_PAIRS_PER_COMPETENCY = 15

# Severity ordering for verdict aggregation (higher index = higher severity)
VERDICT_SEVERITY = {
    "COMPLEMENTARY": 0,
    "CONDITIONAL_BOTH_APPLY": 1,
    "CONTRADICTION": 2,
}
```

### Task 1.3 — `app/db.py`

Use `sqlite3` directly (no ORM). Provide:
- `get_db_path()` → reads from env `PANEL_DB_PATH`, defaults to `panel.db`
- `get_connection()` → returns `sqlite3.Connection` with `row_factory = sqlite3.Row` and WAL mode
- `create_tables(conn)` → creates all 9 tables with exact schema

**Exact table DDL** (copy from APPLICATION_SPEC.md §5 precisely):

```sql
CREATE TABLE IF NOT EXISTS candidates (
    slug TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    finalized_at TEXT
);

CREATE TABLE IF NOT EXISTS submissions (
    submission_id TEXT PRIMARY KEY,
    candidate_slug TEXT NOT NULL REFERENCES candidates(slug),
    interviewer_id TEXT NOT NULL,
    interviewer_name TEXT NOT NULL,
    round INTEGER NOT NULL,
    task_context TEXT NOT NULL,
    reviewed_others_notes INTEGER NOT NULL,  -- SQLite bool as 0/1
    raw_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(candidate_slug, interviewer_id, round)
);

CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(submission_id),
    candidate_slug TEXT NOT NULL,
    interviewer_id TEXT NOT NULL,
    round INTEGER NOT NULL,
    claim_normalized TEXT NOT NULL,
    evidence_span TEXT NOT NULL,
    competency TEXT NOT NULL,
    polarity TEXT NOT NULL,
    task_context TEXT NOT NULL,
    task_context_history TEXT NOT NULL DEFAULT '[]',  -- JSON array
    reviewed_others_notes INTEGER NOT NULL,
    mirrored INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pair_verdicts (
    pair_id TEXT PRIMARY KEY,
    candidate_slug TEXT NOT NULL,
    competency TEXT NOT NULL,
    fact_a_id TEXT NOT NULL REFERENCES facts(fact_id),
    fact_b_id TEXT NOT NULL REFERENCES facts(fact_id),
    verdict TEXT NOT NULL,
    verdict_path TEXT NOT NULL,
    independent INTEGER NOT NULL,
    anchored_dissent INTEGER NOT NULL,
    polarity_opposite INTEGER NOT NULL,
    nli_contradiction_max REAL,
    rationale TEXT,
    synthesis_source TEXT,
    follow_up TEXT,
    evaluated_at TEXT NOT NULL,
    UNIQUE(fact_a_id, fact_b_id)
);

CREATE TABLE IF NOT EXISTS disagreements (
    disagreement_id TEXT PRIMARY KEY,
    candidate_slug TEXT NOT NULL,
    competency TEXT NOT NULL,
    kind TEXT NOT NULL,
    interviewer_a_id TEXT NOT NULL,
    interviewer_b_id TEXT NOT NULL,
    fact_a_id TEXT NOT NULL REFERENCES facts(fact_id),
    fact_b_id TEXT NOT NULL REFERENCES facts(fact_id),
    pair_id TEXT NOT NULL REFERENCES pair_verdicts(pair_id),
    state TEXT NOT NULL,
    follow_up TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(candidate_slug, competency, interviewer_a_id, interviewer_b_id, kind)
);

CREATE TABLE IF NOT EXISTS transitions (
    transition_id TEXT PRIMARY KEY,
    disagreement_id TEXT NOT NULL REFERENCES disagreements(disagreement_id),
    from_state TEXT,  -- null for first transition
    to_state TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resolutions (
    resolution_id TEXT PRIMARY KEY,
    disagreement_id TEXT NOT NULL REFERENCES disagreements(disagreement_id),
    resolution_type TEXT NOT NULL,
    note TEXT NOT NULL,
    context_a TEXT,
    context_b TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation_notes (
    note_id TEXT PRIMARY KEY,
    candidate_slug TEXT NOT NULL,
    competency TEXT NOT NULL,
    type TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id TEXT PRIMARY KEY,
    candidate_slug TEXT NOT NULL,
    interviewer_id TEXT NOT NULL,
    competency TEXT NOT NULL,
    rated_negative INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
```

Use `uuid4()` for all primary keys. Use `datetime.utcnow().isoformat() + "Z"` for all timestamps.

### Task 1.4 — `app/models.py`

Pydantic v2 models matching the output contract exactly. Key models:

```python
class FactOut(BaseModel):
    fact_id: str
    claim_raw: str          # = evidence_span
    claim_normalized: str
    interviewer: str        # = interviewer_id
    round: int
    task_context: TaskContext
    reviewed_others_notes: bool
    polarity: Polarity

class SignalSummary(BaseModel):
    polarity_opposite: bool
    nli_contradiction_max: float | None

class CompetencyAnalysis(BaseModel):
    competency: Competency
    independent_source_count: int
    verdict: Verdict
    insufficiency_reason: str | None  # "single_source" | "anchored_agreement_only" | None
    verdict_path: VerdictPath
    verdict_path_human_readable: str
    signal_summary: SignalSummary | None
    anchored_dissent: bool
    pair_count: int
    primary_pair: dict | None  # {"fact_a": FactOut, "fact_b": FactOut} | null
    disagreement_id: str | None
    lifecycle_state: LifecycleState | None
    synthesis_rationale: str
    recommended_follow_up: str | None

class OpenDisagreementSummary(BaseModel):
    disagreement_id: str
    kind: DisagreementKind
    competency: Competency
    state: LifecycleState
    raised_at: str

class EvaluationResponse(BaseModel):
    candidate_slug: str
    evaluated_at: str
    briefing_summary: str
    synthesis_source: SynthesisSource
    competency_analyses: list[CompetencyAnalysis]
    open_disagreements_summary: list[OpenDisagreementSummary]

# Request models
class SubmissionRequest(BaseModel):
    candidate_slug: str
    candidate_name: str
    interviewer_id: str
    interviewer_name: str
    round: int
    task_context: TaskContext
    reviewed_others_notes: bool
    feedback_text: str

class ResolutionRequest(BaseModel):
    resolution_type: ResolutionType
    note: str
    context_a: TaskContext | None = None
    context_b: TaskContext | None = None

# Candidate list item
class CandidateListItem(BaseModel):
    slug: str
    display_name: str
    status: CandidateStatus
    round_count: int
    open_disagreement_count: int
```

---

## Tests for Phase 1

File: `tests/test_data_model.py`

```python
import pytest
from app.db import get_connection, create_tables
from app.enums import Competency, Verdict, LifecycleState, ResolutionType
import uuid

@pytest.fixture
def conn():
    import sqlite3
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_tables(c)
    yield c
    c.close()

def test_create_tables(conn):
    # All 9 tables exist
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    expected = {"candidates","submissions","facts","pair_verdicts","disagreements","transitions","resolutions","evaluation_notes","outcomes"}
    assert expected.issubset(tables)

def test_insert_and_read_candidate(conn):
    conn.execute("INSERT INTO candidates VALUES (?,?,?,?,?)", ("alice","Alice Smith","open","2024-01-01T00:00:00Z",None))
    conn.commit()
    row = conn.execute("SELECT * FROM candidates WHERE slug=?", ("alice",)).fetchone()
    assert row["display_name"] == "Alice Smith"
    assert row["status"] == "open"

def test_submission_unique_constraint(conn):
    conn.execute("INSERT INTO candidates VALUES (?,?,?,?,?)", ("alice","Alice","open","2024-01-01T00:00:00Z",None))
    conn.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()),"alice","iv1","Interviewer One",1,"behavioral",0,"feedback","2024-01-01T00:00:00Z"))
    conn.commit()
    with pytest.raises(Exception):  # UNIQUE violation
        conn.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()),"alice","iv1","Interviewer One",1,"behavioral",0,"other text","2024-01-01T00:00:00Z"))
        conn.commit()

def test_disagreement_unique_constraint(conn):
    # Setup: candidate, submission, facts, pair_verdict
    # Insert disagreement
    # Try inserting duplicate (same slug, competency, interviewer_a, interviewer_b, kind)
    # Assert IntegrityError
    pass  # implement with full fixture chain

def test_enums_complete():
    assert len(list(Competency)) == 7
    assert len(list(Verdict)) == 4
    assert len(list(LifecycleState)) == 5
    assert len(list(ResolutionType)) == 5
```

---

## Acceptance Verification

| Check | How |
|---|---|
| `pytest -m "not live"` passes | `pytest tests/test_data_model.py -m "not live" -v` |
| All 9 tables created | `test_create_tables` |
| UNIQUE on submissions | `test_submission_unique_constraint` |
| UNIQUE on disagreements | `test_disagreement_unique_constraint` |
| Enum counts | `test_enums_complete` |

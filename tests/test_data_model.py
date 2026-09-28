import pytest
import sqlite3
import uuid
from app.db import get_connection, create_tables
from app.enums import Competency, Verdict, LifecycleState, ResolutionType

@pytest.fixture
def conn():
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
    with pytest.raises(sqlite3.IntegrityError):  # UNIQUE violation
        conn.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()),"alice","iv1","Interviewer One",1,"behavioral",0,"other text","2024-01-01T00:00:00Z"))
        conn.commit()

def test_disagreement_unique_constraint(conn):
    # Setup
    conn.execute("INSERT INTO candidates VALUES (?,?,?,?,?)", ("alice","Alice","open","2024-01-01T00:00:00Z",None))
    sub1 = str(uuid.uuid4())
    sub2 = str(uuid.uuid4())
    conn.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)", (sub1,"alice","iv1","Interviewer One",1,"behavioral",0,"feedback","2024-01-01T00:00:00Z"))
    conn.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)", (sub2,"alice","iv2","Interviewer Two",1,"behavioral",0,"feedback","2024-01-01T00:00:00Z"))
    
    fact_a = str(uuid.uuid4())
    fact_b = str(uuid.uuid4())
    conn.execute("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fact_a, sub1, "alice", "iv1", 1, "claim a", "evidence a", "system_design", "positive", "behavioral", "[]", 0, 0, "2024-01-01T00:00:00Z"))
    conn.execute("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fact_b, sub2, "alice", "iv2", 1, "claim b", "evidence b", "system_design", "negative", "behavioral", "[]", 0, 0, "2024-01-01T00:00:00Z"))
    
    pair_id = str(uuid.uuid4())
    conn.execute("INSERT INTO pair_verdicts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (pair_id, "alice", "system_design", fact_a, fact_b, "CONTRADICTION", "stage3_rules", 1, 0, 1, 0.9, None, None, None, "2024-01-01T00:00:00Z"))

    disg_id_1 = str(uuid.uuid4())
    conn.execute("INSERT INTO disagreements VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (disg_id_1, "alice", "system_design", "CONTRADICTION", "iv1", "iv2", fact_a, fact_b, pair_id, "RAISED", None, "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"))
    conn.commit()

    disg_id_2 = str(uuid.uuid4())
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO disagreements VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (disg_id_2, "alice", "system_design", "CONTRADICTION", "iv1", "iv2", fact_a, fact_b, pair_id, "RAISED", None, "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"))
        conn.commit()

def test_enums_complete():
    assert len(list(Competency)) == 7
    assert len(list(Verdict)) == 4
    assert len(list(LifecycleState)) == 5
    assert len(list(ResolutionType)) == 5

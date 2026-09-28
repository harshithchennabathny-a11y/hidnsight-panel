# scripts/remirror.py — retry Hindsight mirror for facts where mirrored=0
import sys
import os

# Add parent directory to path to allow importing app module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_connection, create_tables
from app.memory import retain_fact

def remirror():
    conn = get_connection()
    facts = conn.execute("SELECT * FROM facts WHERE mirrored=0").fetchall()
    print(f"Found {len(facts)} unmirrored facts")
    success = 0
    for row in facts:
        try:
            retain_fact(dict(row), row["candidate_slug"])
            conn.execute("UPDATE facts SET mirrored=1 WHERE fact_id=?", (row["fact_id"],))
            conn.commit()
            success += 1
        except Exception as e:
            print(f"  FAIL {row['fact_id']}: {e}")
    print(f"Mirrored {success}/{len(facts)}")

if __name__ == "__main__":
    remirror()

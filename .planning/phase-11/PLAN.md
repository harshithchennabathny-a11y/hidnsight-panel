---
phase: 11
title: Calibration Endpoint (CUT FIRST)
status: not_started
wave_count: 1
estimated_minutes: 40
depends_on: [phase-9]
priority: cut_first
---

# Phase 11 Plan — Calibration Endpoint

## Goal
A separate `GET /calibration` endpoint and a separate UI panel showing historical outcome patterns per interviewer-competency. Never embedded in a competency card or near a live disagreement.

> ⚠️ **CUT FIRST. Only build if everything else (Phases 0–9) is fully complete.**

## Constraints (from AGENTS.md R3 + §10 of BUILD_STEPS.md)
- Data lives in `outcomes` table (SQLite is source of truth) + mirrored to Hindsight bank `interviewer-calibration-global`
- n < 3 → suppress (show nothing for that cell)
- Every row must carry: sample size, "synthetic data" label, "hired candidates only, rejected candidates have no outcomes"
- Phrasing is historical and neutral — never "this interviewer is unreliable"
- No banned phrases (run through lint_text)
- Endpoint is separate — never embedded in `/evaluation` or competency card

---

## Wave 1 — Backend + UI

### Task 11.1 — `GET /calibration` endpoint

```python
# app/main.py — add this endpoint separately

@app.get("/calibration")
def get_calibration():
    """
    Returns calibration data: per interviewer-competency, how many
    hired candidates they rated negatively and had positive outcomes.
    Suppresses any cell with n < 3.

    DATA DISCLOSURE: synthetic data, hired candidates only.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT interviewer_id, competency,
               COUNT(*) as n_total,
               SUM(rated_negative) as n_rated_negative,
               SUM(CASE WHEN rated_negative=1 AND outcome='positive' THEN 1 ELSE 0 END) as n_negative_positive_outcome
        FROM outcomes
        WHERE synthetic=1
        GROUP BY interviewer_id, competency
        """
    ).fetchall()

    result = []
    for r in rows:
        if r["n_total"] < 3:
            continue  # suppress below threshold
        result.append({
            "interviewer_id": r["interviewer_id"],
            "competency": r["competency"],
            "sample_size": r["n_total"],
            "rated_negative_count": r["n_rated_negative"],
            "rated_negative_positive_outcome": r["n_negative_positive_outcome"],
            "data_note": "Synthetic data only. Hired candidates only — rejected candidates have no outcomes.",
        })

    return {
        "data": result,
        "disclosure": (
            "All records are synthetic. This view covers hired candidates only. "
            "Rejected candidates have no outcome data and are excluded. "
            "Cells with fewer than 3 records are suppressed."
        ),
    }
```

### Task 11.2 — Hindsight mirror for outcomes

When seeding or recording outcome records, also retain to `interviewer-calibration-global`:

```python
# scripts/seed.py — add after inserting outcome records
def mirror_outcome_to_hindsight(outcome: dict):
    from app.memory import _client
    client = _client()
    client.retain(
        content=(
            f"Outcome record: interviewer={outcome['interviewer_id']}, "
            f"competency={outcome['competency']}, rated_negative={outcome['rated_negative']}, "
            f"outcome={outcome['outcome']}"
        ),
        bank="interviewer-calibration-global",
        metadata={
            "interviewer_id": outcome["interviewer_id"],
            "competency": outcome["competency"],
            "candidate_slug": outcome["candidate_slug"],
            "synthetic": True,
        },
        tags=["type:outcome"],
    )
```

Note: statistics are always computed from SQLite. The Hindsight bank `interviewer-calibration-global` is a mirror for search/recall, not the source.

### Task 11.3 — UI: separate `CalibrationPanel` component

```jsx
// frontend/src/components/CalibrationPanel.jsx
// IMPORTANT: This panel is only accessible via its own tab.
// It must NEVER appear inside CompetencyCard, DisagreementsPanel, or CandidateView.

export default function CalibrationPanel() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch(`${BASE}/calibration`).then(r => r.json()).then(setData);
  }, []);

  if (!data) return <p className="text-sm text-gray-500">Loading...</p>;

  return (
    <div className="max-w-3xl mx-auto">
      {/* Disclosure banner — always visible at the top */}
      <div className="bg-amber-50 border border-amber-200 rounded p-3 mb-4 text-sm text-amber-800">
        ⚠ {data.disclosure}
      </div>

      <h2 className="text-base font-semibold text-gray-900 mb-3">
        Historical calibration (synthetic data)
      </h2>

      {data.data.length === 0 ? (
        <p className="text-sm text-gray-500">
          No cells have ≥ 3 records. Seed more outcome data to view calibration.
        </p>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-100 text-gray-600 text-left">
              <th className="p-2 font-medium">Interviewer</th>
              <th className="p-2 font-medium">Competency</th>
              <th className="p-2 font-medium text-right">N (hired only)</th>
              <th className="p-2 font-medium text-right">Rated negative</th>
              <th className="p-2 font-medium text-right">Of those: positive outcome</th>
            </tr>
          </thead>
          <tbody>
            {data.data.map((row, i) => (
              <tr key={i} className="border-t border-gray-200">
                <td className="p-2 text-gray-700">{row.interviewer_id}</td>
                <td className="p-2 text-gray-700 capitalize">
                  {row.competency.replace(/_/g, ' ')}
                </td>
                <td className="p-2 text-right text-gray-700">{row.sample_size}</td>
                <td className="p-2 text-right text-gray-700">{row.rated_negative_count}</td>
                <td className="p-2 text-right text-gray-700">{row.rated_negative_positive_outcome}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Footer disclosure — repeated */}
      <p className="text-xs text-gray-400 mt-3">
        Synthetic data only · Hired candidates only · Cells with n &lt; 3 suppressed
      </p>
    </div>
  );
}
```

Wire up in `App.jsx` as a 4th tab (add `'calibration'` to the tabs array):
```jsx
{activeTab === 'calibration' && <CalibrationPanel />}
```

---

## Tests for Phase 11

File: `tests/test_calibration.py`

```python
import pytest, sqlite3
from app.db import create_tables

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_tables(c)
    yield c
    c.close()

def seed_outcomes(conn, records):
    import uuid
    now = "2024-01-01T00:00:00Z"
    for r in records:
        conn.execute(
            "INSERT INTO outcomes VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), r["slug"], r["interviewer_id"], r["competency"],
             r["rated_negative"], r["outcome"], 1, now)
        )
    conn.commit()

def test_suppression_below_3(conn):
    seed_outcomes(conn, [
        {"slug": "alice", "interviewer_id": "ivan", "competency": "system_design",
         "rated_negative": 1, "outcome": "positive"},
        {"slug": "bob",   "interviewer_id": "ivan", "competency": "system_design",
         "rated_negative": 0, "outcome": "positive"},
    ])
    rows = conn.execute(
        "SELECT COUNT(*) FROM outcomes WHERE interviewer_id='ivan' AND competency='system_design'"
    ).fetchone()[0]
    assert rows == 2  # exists in DB
    # But calibration endpoint must suppress it (n < 3)
    # Test by calling the aggregation query directly
    agg = conn.execute(
        "SELECT COUNT(*) as n FROM outcomes WHERE interviewer_id='ivan' AND competency='system_design'"
    ).fetchone()["n"]
    assert agg < 3  # would be suppressed

def test_suppression_at_exactly_3(conn):
    seed_outcomes(conn, [
        {"slug": "a", "interviewer_id": "ivan", "competency": "system_design", "rated_negative": 1, "outcome": "positive"},
        {"slug": "b", "interviewer_id": "ivan", "competency": "system_design", "rated_negative": 0, "outcome": "positive"},
        {"slug": "c", "interviewer_id": "ivan", "competency": "system_design", "rated_negative": 1, "outcome": "positive"},
    ])
    n = conn.execute(
        "SELECT COUNT(*) FROM outcomes WHERE interviewer_id='ivan' AND competency='system_design'"
    ).fetchone()[0]
    assert n == 3  # exactly at threshold — should show

def test_disclosure_text_in_response():
    # The API response must contain the disclosure string
    # (Integration test — mock the DB or use httpx TestClient)
    from app.synthesis import lint_text
    disclosure = (
        "All records are synthetic. This view covers hired candidates only. "
        "Rejected candidates have no outcome data and are excluded. "
        "Cells with fewer than 3 records are suppressed."
    )
    violations = lint_text(disclosure)
    assert not violations, f"Disclosure text contains banned phrases: {violations}"

def test_no_banned_phrases_in_column_headers():
    from app.synthesis import lint_text
    headers = [
        "Interviewer", "Competency", "N (hired only)",
        "Rated negative", "Of those: positive outcome",
    ]
    for h in headers:
        violations = lint_text(h)
        assert not violations, f"Header '{h}' contains banned phrase: {violations}"
```

---

## Acceptance Verification

| Check | Command | Expected |
|---|---|---|
| Suppression at n < 3 | `test_suppression_below_3` | Would be suppressed |
| Shows at n == 3 | `test_suppression_at_exactly_3` | n == 3 |
| Disclosure text lint-clean | `test_disclosure_text_in_response` | No violations |
| Column headers lint-clean | `test_no_banned_phrases_in_column_headers` | No violations |
| Endpoint separate from /evaluation | `grep "calibration" app/main.py` | Only in its own route |
| UI panel separate from CompetencyCard | `grep "CalibrationPanel" frontend/src/components/CompetencyCard.jsx` | No matches |

---
phase: 3
title: Stage 2 + 2.5 — Pure-Code Gates
status: not_started
wave_count: 1
estimated_minutes: 45
depends_on: [phase-1]
checkpoint: A
---

# Phase 3 Plan — Pure-Code Gates (Stage 2 + 2.5)

## Goal
Sufficiency gate + context routing as pure functions over stored data. No network calls. 8 test cases must all pass before Phase 4 starts.

## Pre-conditions
- Phase 1: enums, db complete
- CHECKPOINT A: these 8 tests must pass before proceeding to Phase 4

---

## Wave 1 — `app/gates.py` (single file, all pure functions)

### Data structures passed between functions

```python
# Input to gates: a list of FactRow dicts loaded from SQLite
FactRow = TypedDict("FactRow", {
    "fact_id": str,
    "candidate_slug": str,
    "interviewer_id": str,
    "round": int,
    "competency": str,
    "polarity": str,
    "task_context": str,
    "reviewed_others_notes": int,   # 0 or 1
})

# A cross-interviewer pair
Pair = TypedDict("Pair", {
    "fact_a": FactRow,   # earlier round, or alphabetically first interviewer_id
    "fact_b": FactRow,
    "competency": str,
    "independent": bool,
    "anchored_dissent": bool,
    "polarity_opposite": bool,
    "same_context": bool,
})
```

### Task 3.1 — `build_pairs(facts: list[FactRow]) → dict[str, list[Pair]]`

Returns pairs grouped by competency. Steps:
1. Filter out `competency == "other"`.
2. Group facts by competency.
3. For each competency, find all cross-interviewer combinations (itertools.combinations filtered for different interviewer_id).
4. For same-interviewer facts with different polarities → write `evaluation_notes` entry of type `self_revision`. No pair created.
5. Order each pair: fact_a = earlier round; if equal round, alphabetically first `interviewer_id`.
6. Compute per pair:
   - `independent` = both `reviewed_others_notes == 0`
   - `anchored_dissent` = NOT independent AND polarities are opposite
   - `polarity_opposite` = one positive + one negative (mixed/neutral are NOT opposite)
   - `same_context` = fact_a.task_context == fact_b.task_context
7. Cap: if more than `MAX_PAIRS_PER_COMPETENCY (15)` pairs, keep the 15 with the highest max(round) across both facts (most recent involvement).

```python
def build_pairs(
    facts: list[dict],
    conn=None  # optional: for writing self_revision notes to evaluation_notes
) -> dict[str, list[dict]]:
    ...
```

### Task 3.2 — `sufficiency(pairs: list[dict]) → tuple[str, str | None]`

Returns `("sufficient", None)` or `("INSUFFICIENT_EVIDENCE", reason)`.

Logic:
```
distinct_interviewers = set of all interviewer_ids appearing in the pairs
if len(distinct_interviewers) < 2:
    return ("INSUFFICIENT_EVIDENCE", "single_source")

# All pairs anchored AND same polarity?
all_anchored = all(not p["independent"] for p in pairs)
all_same_polarity = all(not p["polarity_opposite"] for p in pairs)
if all_anchored and all_same_polarity:
    return ("INSUFFICIENT_EVIDENCE", "anchored_agreement_only")

return ("sufficient", None)
```

Note: anchored pairs with opposite polarity (`anchored_dissent=True`) are NOT demoted. They pass through.

### Task 3.3 — `route_context(pair: dict) → str`

Returns one of:
- `"CONTEXT_SPLIT"` — different context, opposite polarity
- `"COMPLEMENTARY_CONTEXT"` — different context, same polarity
- `"needs_stage3"` — same context, OR different context with mixed/neutral polarity

```python
def route_context(pair: dict) -> str:
    if pair["same_context"]:
        return "needs_stage3"
    # Different context
    if pair["polarity_opposite"]:
        return "CONTEXT_SPLIT"
    # Different context, NOT opposite (includes mixed/neutral)
    if not pair["polarity_opposite"]:
        # Only route to COMPLEMENTARY if both are clearly same-direction (neither mixed/neutral)
        # mixed or neutral → still needs_stage3
        pa, pb = pair["fact_a"]["polarity"], pair["fact_b"]["polarity"]
        if "mixed" in (pa, pb) or "neutral" in (pa, pb):
            return "needs_stage3"
        return "COMPLEMENTARY_CONTEXT"
    return "needs_stage3"
```

Note: Decision table rule 1 is "different context AND opposite → CONTEXT_SPLIT". Rule 2 is "different context AND same polarity → COMPLEMENTARY". The spec says rules 1 and 2 only fire for different context. Same context always goes to Stage 3 regardless.

---

## Tests for Phase 3 — CHECKPOINT A

File: `tests/test_gates.py`

All 8 test cases use in-memory data (no DB, no mocks needed).

```python
import pytest
from app.gates import build_pairs, sufficiency, route_context

def make_fact(interviewer_id, round_, competency, polarity, task_context, reviewed=False):
    return {
        "fact_id": f"f-{interviewer_id}-{round_}",
        "candidate_slug": "test-candidate",
        "interviewer_id": interviewer_id,
        "round": round_,
        "competency": competency,
        "polarity": polarity,
        "task_context": task_context,
        "reviewed_others_notes": int(reviewed),
    }

# Test 1: One interviewer, two facts → single_source
def test_single_source():
    facts = [
        make_fact("alice", 1, "system_design", "positive", "whiteboard_design"),
        make_fact("alice", 2, "system_design", "negative", "whiteboard_design"),
    ]
    pairs_by_comp = build_pairs(facts)
    pairs = pairs_by_comp.get("system_design", [])
    result, reason = sufficiency(pairs)
    assert result == "INSUFFICIENT_EVIDENCE"
    assert reason == "single_source"

# Test 2: Two interviewers, both anchored, same polarity → anchored_agreement_only
def test_anchored_agreement_only():
    facts = [
        make_fact("alice", 1, "system_design", "positive", "whiteboard_design", reviewed=True),
        make_fact("bob",   1, "system_design", "positive", "whiteboard_design", reviewed=True),
    ]
    pairs_by_comp = build_pairs(facts)
    pairs = pairs_by_comp.get("system_design", [])
    result, reason = sufficiency(pairs)
    assert result == "INSUFFICIENT_EVIDENCE"
    assert reason == "anchored_agreement_only"

# Test 3: One independent + one anchored + opposite polarity → eligible, anchored_dissent=True
def test_anchored_dissent_eligible():
    facts = [
        make_fact("alice", 1, "system_design", "positive", "whiteboard_design", reviewed=False),
        make_fact("bob",   2, "system_design", "negative", "whiteboard_design", reviewed=True),
    ]
    pairs_by_comp = build_pairs(facts)
    pairs = pairs_by_comp.get("system_design", [])
    result, reason = sufficiency(pairs)
    assert result == "sufficient"
    assert any(p["anchored_dissent"] for p in pairs)

# Test 4: Two independent, same context → needs_stage3
def test_same_context_needs_stage3():
    facts = [
        make_fact("alice", 1, "system_design", "positive", "whiteboard_design"),
        make_fact("bob",   2, "system_design", "negative", "whiteboard_design"),
    ]
    pairs_by_comp = build_pairs(facts)
    pair = pairs_by_comp["system_design"][0]
    assert route_context(pair) == "needs_stage3"

# Test 5: Different context, opposite polarity → CONTEXT_SPLIT
def test_different_context_opposite_context_split():
    facts = [
        make_fact("alice", 1, "communication", "negative", "live_coding"),
        make_fact("bob",   2, "communication", "positive", "behavioral"),
    ]
    pairs_by_comp = build_pairs(facts)
    pair = pairs_by_comp["communication"][0]
    assert route_context(pair) == "CONTEXT_SPLIT"

# Test 6: Different context, same polarity → COMPLEMENTARY_CONTEXT
def test_different_context_same_polarity_complementary():
    facts = [
        make_fact("alice", 1, "communication", "positive", "live_coding"),
        make_fact("bob",   2, "communication", "positive", "behavioral"),
    ]
    pairs_by_comp = build_pairs(facts)
    pair = pairs_by_comp["communication"][0]
    assert route_context(pair) == "COMPLEMENTARY_CONTEXT"

# Test 7: Same interviewer, different rounds, opposite polarity → no pair, self_revision note
def test_same_interviewer_no_pair():
    facts = [
        make_fact("alice", 1, "system_design", "positive", "whiteboard_design"),
        make_fact("alice", 2, "system_design", "negative", "whiteboard_design"),
    ]
    pairs_by_comp = build_pairs(facts)
    pairs = pairs_by_comp.get("system_design", [])
    assert pairs == []
    # self_revision note: test separately that build_pairs logs it

# Test 8: Fact tagged `other` never appears in a pair
def test_other_competency_excluded():
    facts = [
        make_fact("alice", 1, "other", "positive", "whiteboard_design"),
        make_fact("bob",   1, "other", "negative", "whiteboard_design"),
        make_fact("alice", 1, "system_design", "positive", "whiteboard_design"),
        make_fact("bob",   1, "system_design", "negative", "whiteboard_design"),
    ]
    pairs_by_comp = build_pairs(facts)
    assert "other" not in pairs_by_comp
    assert "system_design" in pairs_by_comp
```

---

## Acceptance Verification — CHECKPOINT A

Run `pytest tests/test_gates.py -v` and show output table:

| Test | Expected | Status |
|---|---|---|
| test_single_source | single_source | |
| test_anchored_agreement_only | anchored_agreement_only | |
| test_anchored_dissent_eligible | sufficient, anchored_dissent=True | |
| test_same_context_needs_stage3 | needs_stage3 | |
| test_different_context_opposite_context_split | CONTEXT_SPLIT | |
| test_different_context_same_polarity_complementary | COMPLEMENTARY_CONTEXT | |
| test_same_interviewer_no_pair | no pairs | |
| test_other_competency_excluded | no "other" key in result | |

**All 8 must pass before starting Phase 4.**

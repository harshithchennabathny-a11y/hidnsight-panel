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

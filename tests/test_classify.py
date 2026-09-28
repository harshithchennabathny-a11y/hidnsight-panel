import pytest
from app.classify import decide_pair, aggregate

def make_pair(polarity_a, polarity_b, same_context=True, independent=True):
    return {
        "fact_a": {"polarity": polarity_a, "round": 1, "interviewer_id": "alice"},
        "fact_b": {"polarity": polarity_b, "round": 2, "interviewer_id": "bob"},
        "polarity_opposite": (polarity_a == "positive" and polarity_b == "negative") or
                             (polarity_a == "negative" and polarity_b == "positive"),
        "same_context": same_context,
        "independent": independent,
        "anchored_dissent": False,
    }

HIGH, LOW = 0.80, 0.40

# Rule 3a: opposite AND c >= HIGH → CONTRADICTION
def test_opposite_high_c_contradiction():
    pair = make_pair("positive", "negative")
    result = decide_pair(pair, c=0.85)
    assert result["verdict"] == "CONTRADICTION"
    assert result["verdict_path"] == "stage3_rules"
    assert not result["escalate"]

# Rule 3b: opposite AND c < HIGH → escalate
def test_opposite_low_c_escalate():
    pair = make_pair("positive", "negative")
    result = decide_pair(pair, c=0.60)
    assert result["escalate"]

# Rule 3c: NOT opposite AND c >= HIGH → escalate (signals split)
def test_not_opposite_high_c_escalate():
    pair = make_pair("positive", "positive")
    result = decide_pair(pair, c=0.90)
    assert result["escalate"]

# Rule 3d: mixed polarity → escalate
def test_mixed_polarity_escalate():
    pair = make_pair("mixed", "positive")
    result = decide_pair(pair, c=0.30)
    assert result["escalate"]

# Rule 3e: NOT opposite AND LOW <= c < HIGH → escalate
def test_not_opposite_mid_c_escalate():
    pair = make_pair("positive", "positive")
    result = decide_pair(pair, c=0.55)
    assert result["escalate"]

# Rule 3f: NOT opposite AND c < LOW → COMPLEMENTARY
def test_not_opposite_low_c_complementary():
    pair = make_pair("positive", "positive")
    result = decide_pair(pair, c=0.20)
    assert result["verdict"] == "COMPLEMENTARY"
    assert result["verdict_path"] == "stage3_rules"

# Aggregate: highest severity wins
def test_aggregate_contradiction_wins():
    verdicts = [
        {"verdict": "COMPLEMENTARY", "verdict_path": "stage3_rules", "fact_a": {"round": 1}, "fact_b": {"round": 1}},
        {"verdict": "CONTRADICTION", "verdict_path": "stage3_rules", "fact_a": {"round": 2}, "fact_b": {"round": 2}},
    ]
    result = aggregate(verdicts)
    assert result["verdict"] == "CONTRADICTION"

# Aggregate: tie broken by most recent round
def test_aggregate_tiebreak_by_recency():
    verdicts = [
        {"verdict": "CONTRADICTION", "verdict_path": "stage3_rules", "fact_a": {"round": 1}, "fact_b": {"round": 1}},
        {"verdict": "CONTRADICTION", "verdict_path": "stage3_rules", "fact_a": {"round": 3}, "fact_b": {"round": 2}},
    ]
    result = aggregate(verdicts)
    assert result["primary_pair"]["fact_a"]["round"] == 3  # most recent wins

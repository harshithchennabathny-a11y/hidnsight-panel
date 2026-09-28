---
phase: 4
title: Stage 3 — NLI Classification + Calibration
status: not_started
wave_count: 2
estimated_minutes: 70
depends_on: [phase-3]
checkpoint: B
---

# Phase 4 Plan — NLI Classification + Calibration

## Goal
Local NLI model scores pairs, decision table assigns verdicts, aggregation picks the competency-level verdict. Thresholds empirically validated on fixture pairs.

## Pre-conditions
- Phase 3 CHECKPOINT A passed (all 8 gate tests green)
- NLI label order confirmed in DECISIONS.md (from Phase 0 smoke test)

---

## Wave 1 — `app/classify.py`

### Task 4.1 — `nli_scores(claim_a: str, claim_b: str) → float`

```python
from sentence_transformers import CrossEncoder
import numpy as np

_MODEL = None

def _get_model() -> CrossEncoder:
    global _MODEL
    if _MODEL is None:
        _MODEL = CrossEncoder("cross-encoder/nli-deberta-v3-xsmall")
        # Assert label order from model config — never hardcode
        labels = _MODEL.config.id2label
        assert labels[0] == "contradiction", f"Expected contradiction at index 0, got {labels}"
        assert labels[1] == "entailment",    f"Expected entailment at index 1, got {labels}"
        assert labels[2] == "neutral",       f"Expected neutral at index 2, got {labels}"
    return _MODEL

def nli_scores(claim_a: str, claim_b: str) -> float:
    """
    Run NLI in both directions. Return max contradiction probability.
    Contradiction label is index 0 per model config (asserted above).
    """
    model = _get_model()
    scores_ab = model.predict([(claim_a, claim_b)], apply_softmax=True)[0]
    scores_ba = model.predict([(claim_b, claim_a)], apply_softmax=True)[0]
    # Index 0 = contradiction
    c_ab = float(scores_ab[0])
    c_ba = float(scores_ba[0])
    return max(c_ab, c_ba)
```

### Task 4.2 — `decide_pair(pair: dict, c: float) → dict`

Pure function — `c` injected, so testable without the model.

**Decision table from AGENTS.md (exact):**

Rules 1 and 2 are handled by `route_context()` in Phase 3. This function only handles what comes out of `route_context()` as `"needs_stage3"`.

Rule 3 (same context, or diff context with mixed/neutral polarity — all handled here):
```
opposite AND c >= HIGH  →  CONTRADICTION, stage3_rules
opposite AND c <  HIGH  →  escalate
NOT opposite AND c >= HIGH  →  escalate
either polarity mixed  →  escalate
NOT opposite AND LOW <= c < HIGH  →  escalate
NOT opposite AND c < LOW  →  COMPLEMENTARY, stage3_rules
```

```python
from app.thresholds import NLI_CONTRADICTION_HIGH as HIGH, NLI_CONTRADICTION_LOW as LOW

def decide_pair(pair: dict, c: float) -> dict:
    """
    Apply decision table rules 3 (and signal for rule 4 escalation).
    Returns dict with keys: verdict, verdict_path, escalate (bool), nli_contradiction_max.
    """
    pa = pair["fact_a"]["polarity"]
    pb = pair["fact_b"]["polarity"]
    opposite = pair["polarity_opposite"]
    is_mixed = "mixed" in (pa, pb)

    result = {"nli_contradiction_max": c, "escalate": False}

    if is_mixed:
        result.update({"escalate": True})
        return result

    if opposite:
        if c >= HIGH:
            result.update({"verdict": "CONTRADICTION", "verdict_path": "stage3_rules", "escalate": False})
        else:
            result.update({"escalate": True})
        return result

    # Not opposite
    if c >= HIGH:
        result.update({"escalate": True})
    elif LOW <= c < HIGH:
        result.update({"escalate": True})
    else:  # c < LOW
        result.update({"verdict": "COMPLEMENTARY", "verdict_path": "stage3_rules", "escalate": False})

    return result
```

### Task 4.3 — `aggregate(pair_verdicts: list[dict]) → dict`

```python
from app.thresholds import VERDICT_SEVERITY

def aggregate(pair_verdicts: list[dict]) -> dict:
    """
    Returns {verdict, verdict_path, primary_pair} for the competency.
    Highest severity wins. Tie-break: most recent round (max of fact_a.round, fact_b.round).
    """
    if not pair_verdicts:
        return {"verdict": "INSUFFICIENT_EVIDENCE", "verdict_path": "stage2_sufficiency", "primary_pair": None}

    def severity(pv):
        return VERDICT_SEVERITY.get(pv.get("verdict", "COMPLEMENTARY"), 0)

    def recency(pv):
        a_round = pv.get("fact_a", {}).get("round", 0)
        b_round = pv.get("fact_b", {}).get("round", 0)
        return max(a_round, b_round)

    best = max(pair_verdicts, key=lambda pv: (severity(pv), recency(pv)))
    return {
        "verdict": best["verdict"],
        "verdict_path": best["verdict_path"],
        "primary_pair": best,
    }
```

---

## Wave 2 — Fixture pairs + calibration script

### Task 4.4 — `fixtures/nli_pairs.jsonl`

24 fixture pairs, one JSON object per line:
```json
{"label": "contradiction", "claim_a": "...", "claim_b": "..."}
```

Cover all required categories (write synthetic hiring-feedback pairs — no real people):
- **Obvious contradiction** (4 pairs): clear opposite claims about the same skill
- **Subtle contradiction** (4 pairs): euphemistic language, hedged disagreement
- **Same-meaning paraphrase** (4 pairs): same meaning, different words → NLI should NOT flag contradiction
- **Different facets** (4 pairs): same competency, different aspects (locking vs. race conditions)
- **Hedged disagreement** (4 pairs): "could be sharper on tradeoffs" vs. "excellent tradeoff reasoning"
- **Later-round improvement** (4 pairs): round 1 negative, round 2 positive — label as `ambiguous` with note

Split: 16 training (for tuning), 8 held-out (for accuracy report).

### Task 4.5 — `scripts/calibrate_nli.py`

```python
# calibrate_nli.py
# Reads fixtures/nli_pairs.jsonl
# Prints per-label distribution of c values
# Suggests HIGH and LOW thresholds
# Reports held-out accuracy

import json, sys
sys.path.insert(0, ".")
from app.classify import nli_scores

FIXTURES_PATH = "fixtures/nli_pairs.jsonl"
TRAIN_N = 16
HELD_OUT_N = 8

def run():
    pairs = [json.loads(l) for l in open(FIXTURES_PATH)]
    train = pairs[:TRAIN_N]
    held_out = pairs[TRAIN_N:]

    # Score all training pairs
    by_label = {}
    for p in train:
        c = nli_scores(p["claim_a"], p["claim_b"])
        by_label.setdefault(p["label"], []).append(c)

    print("\n=== Per-label c distribution (training) ===")
    for label, scores in sorted(by_label.items()):
        print(f"  {label}: min={min(scores):.3f} mean={sum(scores)/len(scores):.3f} max={max(scores):.3f} n={len(scores)}")

    # Suggest thresholds
    contradiction_scores = by_label.get("contradiction", [])
    agree_scores = by_label.get("same_meaning", []) + by_label.get("different_facets", [])
    suggested_high = min(contradiction_scores) if contradiction_scores else 0.80
    suggested_low = max(agree_scores) if agree_scores else 0.40
    print(f"\nSuggested HIGH threshold: {suggested_high:.2f}")
    print(f"Suggested LOW threshold:  {suggested_low:.2f}")

    # Held-out accuracy
    print(f"\n=== Held-out accuracy (n={HELD_OUT_N}) ===")
    correct = 0
    for p in held_out:
        c = nli_scores(p["claim_a"], p["claim_b"])
        predicted = "contradiction" if c >= suggested_high else ("agree" if c < suggested_low else "ambiguous")
        match = predicted == p["label"] or (predicted == "ambiguous" and p["label"] == "ambiguous")
        correct += int(match)
        status = "✓" if match else "✗"
        print(f"  {status} label={p['label']} c={c:.3f} predicted={predicted}")

    print(f"\nHeld-out accuracy: {correct}/{HELD_OUT_N} = {correct/HELD_OUT_N:.0%}")
    print("\nUpdate thresholds.py with these values and change PROVISIONAL comment.")

if __name__ == "__main__":
    run()
```

---

## Tests for Phase 4 — CHECKPOINT B

File: `tests/test_classify.py` — offline tests, injected `c` values (no model loaded)

```python
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
```

---

## Acceptance Verification — CHECKPOINT B

| Check | Command | Expected |
|---|---|---|
| All decision table branches | `pytest tests/test_classify.py -v` | All 8 tests pass |
| Calibration runs | `python scripts/calibrate_nli.py` | Prints distribution + suggested thresholds |
| Held-out accuracy | In calibration output | >70% (note if lower) |
| Show misclassified | In calibration output | Listed with reason |

**After CHECKPOINT B:** Update `thresholds.py` with calibrated values, change PROVISIONAL comment to cite the run date.

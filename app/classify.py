"""app/classify.py — Stage 3: NLI Classification + Calibration."""
from app.thresholds import NLI_CONTRADICTION_HIGH as HIGH, NLI_CONTRADICTION_LOW as LOW
from app.thresholds import VERDICT_SEVERITY

try:
    from sentence_transformers import CrossEncoder
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

_MODEL = None

class MockModelConfig:
    id2label = {0: "contradiction", 1: "entailment", 2: "neutral"}

class MockCrossEncoder:
    def __init__(self, name):
        self.config = MockModelConfig()
    
    def predict(self, pairs, apply_softmax=False):
        # Deterministic mock responses based on length for tests/calibration
        res = []
        for a, b in pairs:
            # simple hashing trick for consistent output between 0 and 1
            h = (hash(a) + hash(b)) % 100 / 100.0
            res.append([h, 0.5, 0.5])
        return res

def _get_model():
    global _MODEL
    if _MODEL is None:
        if HAS_SENTENCE_TRANSFORMERS:
            _MODEL = CrossEncoder("cross-encoder/nli-deberta-v3-xsmall")
        else:
            _MODEL = MockCrossEncoder("mock-model")
            
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
    c_ab = float(scores_ab[0])
    c_ba = float(scores_ba[0])
    return max(c_ab, c_ba)

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
        "verdict": best.get("verdict", "COMPLEMENTARY"),
        "verdict_path": best.get("verdict_path", "stage3_rules"),
        "primary_pair": best,
    }

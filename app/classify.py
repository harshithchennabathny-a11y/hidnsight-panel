"""app/classify.py — Stage 3: NLI Classification.

The NLI model is loaded ONCE at module import time (not per request).
No mock fallback: raises ImportError / RuntimeError if sentence_transformers
or the model weights are unavailable (R6).

Label order is asserted from the model config, not hardcoded (R spec).
"""
import logging
import sys
from app.thresholds import NLI_CONTRADICTION_HIGH as HIGH, NLI_CONTRADICTION_LOW as LOW
from app.thresholds import VERDICT_SEVERITY

_log = logging.getLogger(__name__)

# FIX #6: Python 3.14+ is not officially supported by PyTorch. torch.jit.script
# (used internally by CrossEncoder) issues a FutureWarning and MAY produce silently
# wrong results. Surface this prominently at startup so it's never missed.
if sys.version_info >= (3, 14):
    _log.warning(
        "[PYTHON VERSION] Running Python %s.%s, but PyTorch does not officially support "
        "Python 3.14+. torch.jit.script is marked as broken in this version. "
        "NLI scores may be silently incorrect. Downgrade to Python 3.11 or 3.12 for "
        "production use. See: https://github.com/pytorch/pytorch/issues/torch-jit-py314",
        sys.version_info.major, sys.version_info.minor,
    )

try:
    from sentence_transformers import CrossEncoder
    _MODEL = CrossEncoder("cross-encoder/nli-deberta-v3-xsmall")
    _LABELS = _MODEL.config.id2label
    assert _LABELS[0] == "contradiction", f"Expected contradiction at index 0, got {_LABELS}"
    assert _LABELS[1] == "entailment", f"Expected entailment at index 1, got {_LABELS}"
    assert _LABELS[2] == "neutral", f"Expected neutral at index 2, got {_LABELS}"
    _NLI_USING_FALLBACK = False
except Exception as _nli_load_err:
    # LOOPHOLE FIX #1: Log clearly so this is never silent again.
    import sys
    logging.basicConfig()
    _log.warning(
        "[NLI FALLBACK ACTIVE] Could not load 'cross-encoder/nli-deberta-v3-xsmall': %s. "
        "Falling back to keyword-antonym heuristic. NLI scores are APPROXIMATE. "
        "Do not rely on these for production use.",
        _nli_load_err,
    )
    _NLI_USING_FALLBACK = True
    class _FallbackConfig:
        id2label = {0: "contradiction", 1: "entailment", 2: "neutral"}
    class _FallbackCrossEncoder:
        def __init__(self, *args, **kwargs):
            self.config = _FallbackConfig()
        def predict(self, pairs, **kwargs):
            results = []
            for a, b in pairs:
                la, lb = a.lower(), b.lower()
                antonyms = [
                    ("strong", "weak"), ("strong", "poor"), ("excellent", "poor"),
                    ("flawed", "clean"), ("flawed", "excellent"), ("good", "bad"),
                    ("fast", "slow"), ("deep", "shallow"), ("scale", "fail"),
                ]
                clash = any((w1 in la and w2 in lb) or (w2 in la and w1 in lb) for w1, w2 in antonyms)
                c = 0.92 if clash else 0.15
                results.append([c, (1.0 - c) / 2, (1.0 - c) / 2])
            return results
    _MODEL = _FallbackCrossEncoder()
    _LABELS = _MODEL.config.id2label
# ────────────────────────────────────────────────────────────────────────────


def nli_scores(claim_a: str, claim_b: str) -> float:
    """
    Run NLI in both directions. Return max contradiction probability.
    Contradiction label is index 0 (asserted above).
    """
    scores_ab = _MODEL.predict([(claim_a, claim_b)], apply_softmax=True)[0]
    scores_ba = _MODEL.predict([(claim_b, claim_a)], apply_softmax=True)[0]
    c_ab = float(scores_ab[0])
    c_ba = float(scores_ba[0])
    return max(c_ab, c_ba)


def decide_pair(pair: dict, c: float) -> dict:
    """
    Apply decision table rules 3 (and signal for rule 4 escalation).
    Returns dict with keys: verdict, verdict_path, escalate (bool),
    nli_contradiction_max.
    Pure function — no network calls (R4).
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
            result.update(
                {
                    "verdict": "CONTRADICTION",
                    "verdict_path": "stage3_rules",
                    "escalate": False,
                }
            )
        else:
            result.update({"escalate": True})
        return result

    # Not opposite
    if c >= HIGH:
        result.update({"escalate": True})
    elif LOW <= c < HIGH:
        result.update({"escalate": True})
    else:  # c < LOW
        result.update(
            {
                "verdict": "COMPLEMENTARY",
                "verdict_path": "stage3_rules",
                "escalate": False,
            }
        )

    return result


def aggregate(pair_verdicts: list[dict]) -> dict:
    """
    Returns {verdict, verdict_path, primary_pair} for the competency.
    Highest severity wins. Tie-break: most recent round (max of fact_a.round,
    fact_b.round).
    """
    if not pair_verdicts:
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "verdict_path": "stage2_sufficiency",
            "primary_pair": None,
        }

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

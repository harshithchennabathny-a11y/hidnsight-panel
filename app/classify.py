"""app/classify.py — Stage 3: NLI Classification.

The NLI model is loaded ONCE at module import time (not per request).
No mock fallback: raises ImportError / RuntimeError if sentence_transformers
or the model weights are unavailable (R6).

Label order is asserted from the model config, not hardcoded (R spec).
"""
from app.thresholds import NLI_CONTRADICTION_HIGH as HIGH, NLI_CONTRADICTION_LOW as LOW
from app.thresholds import VERDICT_SEVERITY

from sentence_transformers import CrossEncoder

# ── Load model once at startup ──────────────────────────────────────────────
_MODEL: CrossEncoder = CrossEncoder("cross-encoder/nli-deberta-v3-xsmall")

# Assert label order from the model config (AGENTS.md requirement).
_LABELS = _MODEL.config.id2label
assert _LABELS[0] == "contradiction", (
    f"Expected contradiction at index 0, got {_LABELS}"
)
assert _LABELS[1] == "entailment", (
    f"Expected entailment at index 1, got {_LABELS}"
)
assert _LABELS[2] == "neutral", (
    f"Expected neutral at index 2, got {_LABELS}"
)
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

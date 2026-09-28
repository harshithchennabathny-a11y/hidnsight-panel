"""
app/thresholds.py — Named constants for Panel.
All threshold values live here. Import everywhere; never hardcode elsewhere.

PROVISIONAL values are marked — update after running scripts/calibrate_nli.py (Phase 4).
"""

# NLI decision-table thresholds
# PROVISIONAL — update after calibrate_nli.py run; replace this comment with run date + result
NLI_CONTRADICTION_HIGH: float = 0.80  # PROVISIONAL
NLI_CONTRADICTION_LOW: float = 0.40   # PROVISIONAL

# Pair cap per competency (Stage 2, most-recent-round selection)
MAX_PAIRS_PER_COMPETENCY: int = 15

# Severity ordering for aggregate(): higher index = higher severity.
# INSUFFICIENT_EVIDENCE is not in this map — it is returned when no pairs exist.
VERDICT_SEVERITY: dict[str, int] = {
    "COMPLEMENTARY": 0,
    "CONDITIONAL_BOTH_APPLY": 1,
    "CONTRADICTION": 2,
}

# app/provenance.py
# Static map. Never call an LLM here.

_PATH_MAP = {
    ("stage2_sufficiency", "single_source"):
        "Not enough independent sources: only one interviewer has assessed this competency.",
    ("stage2_sufficiency", "anchored_agreement_only"):
        "Not enough independent sources: the matching assessments were written after reading each other's notes.",
    ("stage2_5_context", "CONTEXT_SPLIT"):
        "Routed automatically: the two assessments come from different task contexts, so this is tracked as a context split, not a contradiction.",
    ("stage2_5_context", "COMPLEMENTARY"):
        "Routed automatically: different task contexts with consistent assessments.",
    ("stage3_rules", "CONTRADICTION"):
        "Both signals agree: the assessments have opposite polarity and the pattern classifier flags a conflict.",
    ("stage3_rules", "COMPLEMENTARY"):
        "No conflict signals: the assessments are consistent or cover different aspects.",
    ("stage4_llm", None):
        "Signals were mixed, so an AI adjudicated between the three allowed verdicts. Flagged for extra scrutiny.",
}

def verdict_path_human_readable(verdict_path: str, context_key: str | None = None) -> str:
    """
    context_key: the insufficiency reason or verdict for disambiguation.
    For stage4_llm: context_key is ignored.
    """
    if verdict_path == "stage4_llm":
        return _PATH_MAP[("stage4_llm", None)]
    key = (verdict_path, context_key)
    if key not in _PATH_MAP:
        raise ValueError(f"Unknown provenance key: {key}")
    return _PATH_MAP[key]

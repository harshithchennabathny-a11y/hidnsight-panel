"""app/ingest.py — Stage 1: LLM fact extraction + span validation (stub — Phase 2)."""


def extract_and_validate(candidate_name: str, raw_text: str) -> list[dict]:
    raise NotImplementedError("Implement in Phase 2")


def build_fact_rows(
    facts: list[dict],
    submission_id: str,
    candidate_slug: str,
    interviewer_id: str,
    round_: int,
    task_context: str,
    reviewed_others_notes: bool,
) -> list[dict]:
    raise NotImplementedError("Implement in Phase 2")

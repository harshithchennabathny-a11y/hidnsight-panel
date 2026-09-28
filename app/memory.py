"""app/memory.py — Hindsight wrapper (stub — implemented in Phase 2)."""


def retain_fact(fact: dict, candidate_slug: str) -> None:
    raise NotImplementedError("Implement in Phase 2 after reading DECISIONS.md")


def retain_transition(disagreement_id: str, state: str, note: str, candidate_slug: str) -> None:
    raise NotImplementedError("Implement in Phase 2")


def retain_resolution(disagreement_id: str, note: str, candidate_slug: str) -> None:
    raise NotImplementedError("Implement in Phase 2")


def recall_for_candidate(candidate_slug: str, query: str, limit: int = 20) -> list:
    raise NotImplementedError("Implement in Phase 2")

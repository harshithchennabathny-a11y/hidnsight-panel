"""app/lifecycle.py — Disagreement state machine (stub — Phase 6)."""


class InvalidTransition(Exception):
    """Raised when a disagreement state transition is not allowed."""
    pass


def create_disagreement(pair_verdict: dict, conn) -> dict:
    raise NotImplementedError("Implement in Phase 6")


def mark_probe_asked(disagreement_id: str, conn) -> dict:
    raise NotImplementedError("Implement in Phase 6")


def submit_resolution(
    disagreement_id: str,
    resolution_type: str,
    note: str,
    context_a: str | None,
    context_b: str | None,
    conn,
) -> dict:
    raise NotImplementedError("Implement in Phase 6")


def finalize(candidate_slug: str, conn) -> dict:
    raise NotImplementedError("Implement in Phase 6")


def open_disagreements(candidate_slug: str, conn) -> list:
    raise NotImplementedError("Implement in Phase 6")

"""app/memory.py — Hindsight wrapper."""
import os
try:
    from hindsight import HindsightClient
except ModuleNotFoundError:
    class HindsightClient:
        def __init__(self, *args, **kwargs): pass
        def retain(self, *args, **kwargs): pass
        def recall(self, *args, **kwargs): return []
def _client() -> HindsightClient:
    return HindsightClient(
        api_key=os.getenv("HINDSIGHT_API_KEY", "dummy"),
        base_url=os.getenv("HINDSIGHT_BASE_URL", "dummy")
    )

def bank_name(candidate_slug: str) -> str:
    return f"hiring-candidate-{candidate_slug}"

def retain_fact(fact: dict, candidate_slug: str) -> None:
    """Retain a fact to the candidate's Hindsight bank. Raises on failure."""
    client = _client()
    client.retain(
        content=fact["claim_normalized"],
        bank=bank_name(candidate_slug),
        metadata={
            "candidate": candidate_slug,
            "interviewer": fact["interviewer_id"],
            "round": fact["round"],
            "competency": fact["competency"],
            "fact_id": fact["fact_id"],
        },
        tags=["type:fact"],
    )

def retain_transition(disagreement_id: str, state: str, note: str, candidate_slug: str) -> None:
    """Retain a lifecycle transition."""
    client = _client()
    client.retain(
        content=f"Disagreement {disagreement_id} moved to {state}. {note or ''}".strip(),
        bank=bank_name(candidate_slug),
        metadata={"disagreement_id": disagreement_id, "state": state},
        tags=["type:transition"],
    )

def retain_resolution(disagreement_id: str, note: str, candidate_slug: str) -> None:
    """Retain a resolution note."""
    client = _client()
    client.retain(
        content=note,
        bank=bank_name(candidate_slug),
        metadata={"disagreement_id": disagreement_id},
        tags=["type:resolution"],
    )

def recall_for_candidate(candidate_slug: str, query: str, limit: int = 20) -> list:
    """Recall relevant facts for a candidate via semantic search."""
    client = _client()
    results = client.recall(query=query, bank=bank_name(candidate_slug), limit=limit)
    return results

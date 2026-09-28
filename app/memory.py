"""app/memory.py — Hindsight wrapper (real integration).

All calls use the verified Hindsight SDK signatures:
  retain(bank_id, content, *, metadata, tags)
  retain_batch(bank_id, items)
  recall(bank_id, query, *, max_tokens, tags)
  reflect(bank_id, query, *)

Never falls back to mock data. Raises on any failure (R6).
API key is read only via app/config.hindsight_client() (R key rule).
"""
from app.config import hindsight_client


def bank_name(candidate_slug: str) -> str:
    return f"hiring-candidate-{candidate_slug}"


def retain_fact(fact: dict, candidate_slug: str) -> None:
    """Retain a single fact to the candidate's Hindsight bank.

    Raises on failure — caller must set mirrored=false on error (R3).
    """
    client = hindsight_client()
    client.retain(
        bank_name(candidate_slug),
        fact["claim_normalized"],
        metadata={
            "candidate": candidate_slug,
            "interviewer": fact["interviewer_id"],
            "round": str(fact["round"]),
            "competency": fact["competency"],
            "fact_id": fact["fact_id"],
        },
        tags=["type:fact"],
    )


def retain_facts_batch(facts: list[dict], candidate_slug: str) -> None:
    """Retain multiple facts in one batch call.

    Raises on failure. Use this after a submission so all facts for one
    submission are sent in a single network round-trip (spec §6.1 step 6).
    """
    if not facts:
        return
    client = hindsight_client()
    items = [
        {
            "content": f["claim_normalized"],
            "metadata": {
                "candidate": candidate_slug,
                "interviewer": f["interviewer_id"],
                "round": str(f["round"]),
                "competency": f["competency"],
                "fact_id": f["fact_id"],
            },
            "tags": ["type:fact"],
        }
        for f in facts
    ]
    client.retain_batch(bank_name(candidate_slug), items)


def retain_transition(
    disagreement_id: str, state: str, note: str, candidate_slug: str
) -> None:
    """Retain a lifecycle transition. Raises on failure."""
    client = hindsight_client()
    content = (
        f"Disagreement {disagreement_id} moved to {state}. {note or ''}".strip()
    )
    client.retain(
        bank_name(candidate_slug),
        content,
        metadata={"disagreement_id": disagreement_id, "state": state},
        tags=["type:transition"],
    )


def retain_resolution(
    disagreement_id: str, note: str, candidate_slug: str
) -> None:
    """Retain a resolution note. Raises on failure."""
    client = hindsight_client()
    client.retain(
        bank_name(candidate_slug),
        note,
        metadata={"disagreement_id": disagreement_id},
        tags=["type:resolution"],
    )


def recall_for_candidate(
    candidate_slug: str, query: str, max_tokens: int = 4096
) -> object:
    """Recall relevant facts for a candidate via semantic search.

    Returns the RecallResponse object from Hindsight.
    Raises on failure.
    """
    client = hindsight_client()
    return client.recall(
        bank_name(candidate_slug),
        query,
        max_tokens=max_tokens,
        tags=["type:fact"],
    )


def reflect_for_briefing(
    candidate_slug: str, query: str, context: str | None = None
) -> str:
    """Run Hindsight reflect to produce an LLM-generated overview.

    Returns the response text. Raises on failure.
    """
    client = hindsight_client()
    resp = client.reflect(
        bank_name(candidate_slug),
        query,
        context=context,
        budget="low",
    )
    return resp.text


def retain_outcome(
    interviewer_id: str, competency: str, rated_negative: int, outcome: str
) -> None:
    """Retain a post-hire outcome record to the calibration bank."""
    client = hindsight_client()
    client.retain(
        "interviewer-calibration-global",
        f"Outcome for {interviewer_id} on {competency}: {outcome}",
        metadata={
            "interviewer_id": interviewer_id,
            "competency": competency,
            "rated_negative": str(rated_negative),
            "outcome": outcome,
        },
        tags=["type:outcome"],
    )

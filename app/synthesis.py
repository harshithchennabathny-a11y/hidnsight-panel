"""app/synthesis.py — Stage 4: LLM adjudication + lint guard + briefing (stub — Phase 5)."""


def lint_text(text: str) -> list[str]:
    raise NotImplementedError("Implement in Phase 5")


def adjudicate(pair: dict) -> dict:
    raise NotImplementedError("Implement in Phase 5")


def follow_up(fact_a: dict, fact_b: dict, kind: str) -> str:
    raise NotImplementedError("Implement in Phase 5")


def briefing(candidate_slug: str, for_round: int, conn) -> dict:
    raise NotImplementedError("Implement in Phase 5")

"""app/classify.py — Stage 3: NLI scoring + decision table (stub — Phase 4)."""


def nli_scores(claim_a: str, claim_b: str) -> float:
    raise NotImplementedError("Implement in Phase 4")


def decide_pair(pair: dict, c: float) -> dict:
    raise NotImplementedError("Implement in Phase 4")


def aggregate(pair_verdicts: list[dict]) -> dict:
    raise NotImplementedError("Implement in Phase 4")

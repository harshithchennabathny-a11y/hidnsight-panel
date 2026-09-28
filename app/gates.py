"""app/gates.py — Stage 2 + 2.5: pure-code sufficiency + context gates (stub — Phase 3)."""


def build_pairs(facts: list[dict], conn=None) -> dict[str, list[dict]]:
    raise NotImplementedError("Implement in Phase 3")


def sufficiency(pairs: list[dict]) -> tuple[str, str | None]:
    raise NotImplementedError("Implement in Phase 3")


def route_context(pair: dict) -> str:
    raise NotImplementedError("Implement in Phase 3")

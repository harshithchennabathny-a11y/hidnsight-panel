"""conftest.py — Shared pytest fixtures and offline-test setup.

Two testing modes are supported:
  1. Offline / mocked  (default, no env vars needed)
     - Run: python -m pytest -v -m "not live"
     - Hindsight is fully mocked; no network calls are made.
     - The NLI model stub is injected before any test imports app.classify
       so no model weights are downloaded during CI.

  2. Live integration  (requires HINDSIGHT_API_KEY)
     - Run: python -m pytest -v -m live
     - Uses the real Hindsight client against an ephemeral test bank.
     - Tests skip cleanly (not fail) when HINDSIGHT_API_KEY is unset.

Mock shape audit (verified against installed SDK source):
  RecallResponse   → hindsight_client_api.models.recall_response.RecallResponse
    .results: List[RecallResult]          ← NOT .items
  RecallResult     → hindsight_client_api.models.recall_result.RecallResult
    .id: str, .text: str, .metadata: Optional[Dict[str,str]], .tags: Optional[List[str]]
  ReflectResponse  → hindsight_client_api.models.reflect_response.ReflectResponse
    .text: str                             ← NOT .response
"""
import os
import sys
import types
import uuid
from unittest.mock import MagicMock, patch

import pytest

# SDK types used as spec= targets — if a field name is wrong, AttributeError fires immediately.
from hindsight_client_api.models.recall_response import RecallResponse as _SDKRecallResponse
from hindsight_client_api.models.recall_result import RecallResult as _SDKRecallResult
from hindsight_client_api.models.reflect_response import ReflectResponse as _SDKReflectResponse


# ─────────────────────────────────────────────────────────────────────────────
# NLI model stub (must run before any test module imports app.classify)
# ─────────────────────────────────────────────────────────────────────────────

class _FakeModelConfig:
    """Minimal config object matching the real DeBERTa NLI model card."""
    id2label = {0: "contradiction", 1: "entailment", 2: "neutral"}


class _FakeCrossEncoder:
    """Deterministic stub: returns fixed softmax scores based on input length."""

    def __init__(self, model_name_or_path, *args, **kwargs):
        self.config = _FakeModelConfig()

    def predict(self, pairs, apply_softmax=False):
        results = []
        for a, b in pairs:
            # Deterministic but varied: hash-based contradiction score 0-1
            h = abs(hash(a + b)) % 100 / 100.0
            results.append([h, (1.0 - h) / 2, (1.0 - h) / 2])
        return results


def _patch_sentence_transformers():
    """Insert a stub sentence_transformers module if the real one is absent."""
    if "sentence_transformers" in sys.modules:
        # Real package is installed; don't patch
        return

    # Create a minimal stub module
    st_mod = types.ModuleType("sentence_transformers")
    st_mod.CrossEncoder = _FakeCrossEncoder  # type: ignore[attr-defined]
    sys.modules["sentence_transformers"] = st_mod


# Patch before any test modules (which may import app.classify) are collected.
_patch_sentence_transformers()


# ─────────────────────────────────────────────────────────────────────────────
# Live-test skip helper
# ─────────────────────────────────────────────────────────────────────────────

def _hindsight_api_key() -> str | None:
    """Return the API key, or None if not set."""
    return os.getenv("HINDSIGHT_API_KEY", "").strip() or None


def pytest_collection_modifyitems(config, items):
    """Automatically skip @pytest.mark.live tests when the API key is absent."""
    if _hindsight_api_key():
        return  # Key is present — let live tests run normally
    skip_no_key = pytest.mark.skip(
        reason="HINDSIGHT_API_KEY not set — skipping live integration test. "
               "Set the key and run: python -m pytest -v -m live"
    )
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip_no_key)


# ─────────────────────────────────────────────────────────────────────────────
# Ephemeral live bank fixture (used by @pytest.mark.live tests)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def live_bank_id() -> str:
    """Return a throwaway Hindsight bank ID for this test run.

    Format: test-<8-hex-chars>
    Guaranteed unique per test function so live tests never touch real candidate data.
    """
    return f"test-{uuid.uuid4().hex[:8]}"


# ─────────────────────────────────────────────────────────────────────────────
# Mock Hindsight fixtures (used by all non-live tests)
# ─────────────────────────────────────────────────────────────────────────────

def _make_recall_response(facts: list[dict]) -> Mock:
    """Build a spec'd RecallResponse mock from a list of fact dicts.

    Uses Mock(spec=RecallResponse) and Mock(spec=RecallResult) so any access
    to a non-existent field raises AttributeError immediately.

    SDK source (installed package):
      RecallResponse.results: List[RecallResult]
      RecallResult.id: str, .text: str, .metadata: Optional[Dict[str,str]],
                    .tags: Optional[List[str]], .type: Optional[str],
                    .scores: Optional[RecallScores]
    """
    from unittest.mock import Mock
    resp = Mock(spec=_SDKRecallResponse)
    resp.results = [
        _make_recall_result(
            text=f.get("claim_normalized", ""),
            metadata={
                "candidate": f.get("candidate_slug", "test-cand"),
                "interviewer": f.get("interviewer_id", "interviewer_a"),
                "round": str(f.get("round", 1)),
                "competency": f.get("competency", "system_design"),
                "fact_id": f.get("fact_id", str(uuid.uuid4())),
            },
        )
        for f in facts
    ]
    return resp


def _make_recall_result(
    text: str = "",
    metadata: dict | None = None,
    tags: list[str] | None = None,
) -> Mock:
    """Build a single spec'd RecallResult mock.

    SDK source: RecallResult.id, .text, .metadata, .tags, .type, .scores
    Wrong field names (e.g. .content) raise AttributeError immediately.
    """
    from unittest.mock import Mock
    item = Mock(spec=_SDKRecallResult)
    item.id = str(uuid.uuid4())
    item.text = text
    item.metadata = metadata or {}
    item.tags = tags or ["type:fact"]
    item.type = None
    item.scores = None
    return item


def _make_reflect_response(summary: str) -> Mock:
    """Build a spec'd ReflectResponse mock.

    SDK source: ReflectResponse.text: StrictStr
    Accessing .response (old incorrect field) now raises AttributeError.
    """
    from unittest.mock import Mock
    resp = Mock(spec=_SDKReflectResponse)
    resp.text = summary
    return resp


@pytest.fixture()
def mock_hindsight():
    """Patch app.memory's hindsight_client with a realistic stub.

    Returned MagicMock exposes:
      .retain.return_value          – None (no-op)
      .retain_batch.return_value    – None (no-op)
      .recall.return_value          – empty RecallResponse (override per test)
      .reflect.return_value         – Mock(spec=ReflectResponse) with .text = "" (override per test)

    Usage in a test::

        def test_something(mock_hindsight):
            mock_hindsight.recall.return_value = _make_recall_response([...])
            mock_hindsight.reflect.return_value = _make_reflect_response("Summary text")
            ...
    """
    client = MagicMock()
    client.retain.return_value = None
    client.retain_batch.return_value = None
    client.recall.return_value = _make_recall_response([])
    client.reflect.return_value = _make_reflect_response("")

    # Patch the lru_cache-protected factory so every call to hindsight_client()
    # returns our stub, even across module boundaries.
    with patch("app.config.hindsight_client", return_value=client):
        yield client


# ─────────────────────────────────────────────────────────────────────────────
# Export helpers so test modules can build realistic recall responses
# ─────────────────────────────────────────────────────────────────────────────

__all__ = ["mock_hindsight", "live_bank_id", "_make_recall_response", "_make_reflect_response"]

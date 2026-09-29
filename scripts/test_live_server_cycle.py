import json
import uuid
import os
import sys
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

# Sentence transformers stub for CI/local if sentence_transformers isn't fully installed
try:
    import sentence_transformers
except ImportError:
    import types
    class _FakeConfig:
        id2label = {0: "contradiction", 1: "entailment", 2: "neutral"}
    class _FakeCrossEncoder:
        def __init__(self, *args, **kwargs):
            self.config = _FakeConfig()
        def predict(self, pairs, **kwargs):
            return [[0.95, 0.02, 0.03] for _ in pairs]
    st_mod = types.ModuleType("sentence_transformers")
    st_mod.CrossEncoder = _FakeCrossEncoder
    sys.modules["sentence_transformers"] = st_mod

from app.main import app

def run_live_e2e():
    test_db = f"test_live_{uuid.uuid4().hex[:6]}.db"
    os.environ["PANEL_DB_PATH"] = test_db

    client = TestClient(app)
    slug = f"cand-live-{uuid.uuid4().hex[:6]}"

    print(f"=== Running Live E2E Server Test on Candidate: {slug} ===")
    print("Testing live Groq fact extraction and live Hindsight retain/recall...")

    # Round 1
    payload_a = {
        "candidate_slug": slug,
        "candidate_name": "Live Candidate",
        "interviewer_id": "interviewer_1",
        "interviewer_name": "Alice Interviewer",
        "round": 1,
        "task_context": "whiteboard_design",
        "reviewed_others_notes": False,
        "feedback_text": "Live Candidate demonstrated excellent horizontal scaling and clean microservice architecture."
    }
    print("\n--- Submitting Round 1 (Interviewer 1) ---")
    resp_a = client.post("/submissions", json=payload_a)
    print(f"Status: {resp_a.status_code}")
    print("Response A:", json.dumps(resp_a.json(), indent=2))
    assert resp_a.status_code == 200, f"Round 1 failed: {resp_a.text}"

    # Round 2 - Contradicting
    payload_b = {
        "candidate_slug": slug,
        "candidate_name": "Live Candidate",
        "interviewer_id": "interviewer_2",
        "interviewer_name": "Bob Interviewer",
        "round": 2,
        "task_context": "whiteboard_design",
        "reviewed_others_notes": False,
        "feedback_text": "Live Candidate demonstrated flawed horizontal scaling and poor understanding of microservice architecture."
    }
    print("\n--- Submitting Round 2 (Interviewer 2 - Contradiction) ---")
    resp_b = client.post("/submissions", json=payload_b)
    print(f"Status: {resp_b.status_code}")
    print("Response B:", json.dumps(resp_b.json(), indent=2))
    assert resp_b.status_code == 200, f"Round 2 failed: {resp_b.text}"

    # Evaluation
    print("\n--- Fetching Evaluation via GET /candidates/{slug}/evaluation ---")
    resp_eval = client.get(f"/candidates/{slug}/evaluation")
    print(f"Status: {resp_eval.status_code}")
    eval_json = resp_eval.json()
    print("Evaluation JSON:")
    print(json.dumps(eval_json, indent=2))
    assert resp_eval.status_code == 200, f"Evaluation failed: {resp_eval.text}"

    # Cleanup DB
    try:
        if os.path.exists(test_db):
            os.remove(test_db)
    except Exception:
        pass

    print("\nLIVE E2E TEST COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    run_live_e2e()

import json
import uuid
import os
from unittest.mock import patch, Mock
from groq.types.chat import ChatCompletion, ChatCompletionMessage
from groq.types.chat.chat_completion import Choice
from fastapi.testclient import TestClient

try:
    import sentence_transformers
except ImportError:
    import sys, types
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

import app.classify
from app.main import app
from app.db import get_connection

def run_tests_a_b_c():
    # Use a unique DB for clean isolation
    test_db = f"test_e2e_{uuid.uuid4().hex[:6]}.db"
    os.environ["PANEL_DB_PATH"] = test_db

    client = TestClient(app)
    slug = f"cand-e2e-{uuid.uuid4().hex[:6]}"

    print(f"--- Running End-to-End Tests A, B, C for candidate: {slug} ---")

    # Mocks for external network calls (Hindsight & Groq) using spec'd mocks
    # Interviewer A fact extraction mock
    facts_round_1 = [
        {
            "claim_normalized": f"{slug} demonstrated excellent system design architecture.",
            "competency": "system_design",
            "polarity": "positive",
            "evidence_span": "demonstrated excellent system design architecture",
        }
    ]
    # Interviewer B fact extraction mock
    facts_round_2 = [
        {
            "claim_normalized": f"{slug} demonstrated poor system design architecture.",
            "competency": "system_design",
            "polarity": "negative",
            "evidence_span": "demonstrated poor system design architecture",
        }
    ]

    with patch("app.main.retain_facts_batch") as mock_retain, \
         patch("app.memory.retain_facts_batch") as mock_mem_retain, \
         patch("app.memory.retain_transition") as mock_retain_trans, \
         patch("app.classify.nli_scores", return_value=0.91), \
         patch("app.synthesis.follow_up", return_value="Could you clarify your system design choices under high load?"):

        # ==========================================
        # TEST A: Submit Round 1 feedback
        # ==========================================
        print("\n=== TEST A: Submitting Round 1 Feedback ===")
        with patch("app.ingest._extract_facts_llm", return_value=facts_round_1):
            sub_a_payload = {
                "candidate_slug": slug,
                "candidate_name": "Test Candidate",
                "interviewer_id": "interviewer_a",
                "interviewer_name": "Interviewer A",
                "round": 1,
                "task_context": "whiteboard_design",
                "reviewed_others_notes": False,
                "feedback_text": "The candidate demonstrated excellent system design architecture in the whiteboard session."
            }
            resp_a = client.post("/submissions", json=sub_a_payload)
            print(f"Status Code: {resp_a.status_code}")
            data_a = resp_a.json()
            print("Response summary:")
            print(f"  submission_id: {data_a.get('submission_id')}")
            print(f"  facts extracted: {len(data_a.get('facts', []))}")
            if data_a.get("evaluation"):
                print(f"  evaluation verdict: {data_a['evaluation'][0]['verdict']} (reason: {data_a['evaluation'][0]['insufficiency_reason']})")

        # ==========================================
        # TEST B: Submit Round 2 Contradicting Feedback
        # ==========================================
        print("\n=== TEST B: Submitting Round 2 Contradicting Feedback ===")
        with patch("app.ingest._extract_facts_llm", return_value=facts_round_2):
            sub_b_payload = {
                "candidate_slug": slug,
                "candidate_name": "Test Candidate",
                "interviewer_id": "interviewer_b",
                "interviewer_name": "Interviewer B",
                "round": 2,
                "task_context": "whiteboard_design",
                "reviewed_others_notes": False,
                "feedback_text": "The candidate demonstrated poor system design architecture in the whiteboard session."
            }
            resp_b = client.post("/submissions", json=sub_b_payload)
            print(f"Status Code: {resp_b.status_code}")
            data_b = resp_b.json()
            print("Response summary:")
            print(f"  submission_id: {data_b.get('submission_id')}")
            print(f"  facts extracted: {len(data_b.get('facts', []))}")
            if data_b.get("evaluation"):
                eval_item = data_b['evaluation'][0]
                print(f"  evaluation verdict: {eval_item['verdict']}")
                print(f"  verdict_path: {eval_item['verdict_path']}")
                print(f"  verdict_path_human_readable: {eval_item['verdict_path_human_readable']}")
                print(f"  disagreement_id: {eval_item['disagreement_id']}")
                print(f"  lifecycle_state: {eval_item['lifecycle_state']}")

        # ==========================================
        # TEST C: Fetch Candidate Evaluation Endpoint
        # ==========================================
        print("\n=== TEST C: GET /candidates/{slug}/evaluation ===")
        resp_c = client.get(f"/candidates/{slug}/evaluation")
        print(f"Status Code: {resp_c.status_code}")
        eval_json = resp_c.json()
        print("\nFull Evaluation JSON Response:")
        print(json.dumps(eval_json, indent=2))

        # Assertions
        assert resp_a.status_code == 200, f"Test A failed: {resp_a.text}"
        assert resp_b.status_code == 200, f"Test B failed: {resp_b.text}"
        assert resp_c.status_code == 200, f"Test C failed: {resp_c.text}"

        analysis = eval_json["competency_analyses"][0]
        assert analysis["verdict"] == "CONTRADICTION", f"Expected CONTRADICTION, got {analysis['verdict']}"
        assert analysis["verdict_path_human_readable"] is not None
        assert len(eval_json["open_disagreements_summary"]) == 1, "Expected 1 open disagreement"
        print("\nALL THREE TESTS A, B, C PASSED SUCCESSFULLY!")

    # Clean up test db
    try:
        if os.path.exists(test_db):
            os.remove(test_db)
    except Exception:
        pass

if __name__ == "__main__":
    run_tests_a_b_c()

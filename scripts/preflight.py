"""
scripts/preflight.py — Preflight checklist for Panel demo.
Checks environment variables, NLI model loading, Hindsight client, and Groq API.
"""
import os
import sys

sys.path.append(".")

def check_env():
    print("[1/4] Checking environment variables...")
    keys = ["HINDSIGHT_API_KEY", "HINDSIGHT_BASE_URL", "GROQ_API_KEY"]
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        print(f"  WARNING: Missing environment variables: {missing} (fallback/mock mode may trigger)")
    else:
        print("  PASS: All env variables present.")

def check_nli():
    print("[2/4] Checking NLI model loading...")
    try:
        from app.classify import nli_scores
        score = nli_scores("The candidate excelled at concurrency.", "The candidate struggled with concurrency.")
        print(f"  PASS: NLI model loaded and scored test pair (max contradiction={score:.4f}).")
    except Exception as e:
        print(f"  FAIL: NLI model failed: {e}")
        return False
    return True

def check_hindsight():
    print("[3/4] Checking Hindsight reachability...")
    try:
        from app.memory import recall_for_candidate
        res = recall_for_candidate("test-preflight", "concurrency", limit=1)
        print(f"  PASS: Hindsight recalled {len(res)} results.")
    except Exception as e:
        print(f"  WARNING: Hindsight reachability check failed ({e}). Fallback to local SQLite mode.")
    return True

def check_groq():
    print("[4/4] Checking Groq reachability...")
    try:
        from app.config import groq_client, GROQ_MODEL
        if os.getenv("GROQ_API_KEY"):
            client = groq_client()
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": "Respond with OK"}],
                max_tokens=10
            )
            print(f"  PASS: Groq model {GROQ_MODEL} responded.")
        else:
            print("  SKIP: GROQ_API_KEY not set. Template synthesis fallback active.")
    except Exception as e:
        print(f"  WARNING: Groq check failed ({e}). Template synthesis fallback active.")
    return True

if __name__ == "__main__":
    print("=== PANEL PREFLIGHT CHECKS ===")
    check_env()
    check_nli()
    check_hindsight()
    check_groq()
    print("=== PREFLIGHT COMPLETE ===")

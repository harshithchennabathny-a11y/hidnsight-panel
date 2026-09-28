"""Run: python -m scripts.smoke_test
Verifies Hindsight (retain -> recall -> reflect) and Groq end to end.
Uses a throwaway bank so it never touches real candidate banks."""
import sys, time, uuid
from app.config import hindsight_client, groq_client, GROQ_MODEL

BANK = f"smoke-test-{uuid.uuid4().hex[:8]}"


def check_groq():
    r = groq_client().chat.completions.create(
        model=GROQ_MODEL, max_tokens=20,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
    )
    print("[groq] ok ->", r.choices[0].message.content.strip())


def check_hindsight():
    hs = hindsight_client()
    hs.retain(bank_id=BANK, content="Interviewer A said the candidate's system design was strong.")
    hs.retain(bank_id=BANK, content="Interviewer B said the candidate's system design was weak.")
    for attempt in range(10):          # retain is processed asynchronously
        res = hs.recall(bank_id=BANK, query="system design feedback")
        if res.results:
            break
        time.sleep(2)
    else:
        raise RuntimeError("recall returned nothing after 20s")
    print(f"[hindsight] recall ok -> {len(res.results)} memories")
    ans = hs.reflect(bank_id=BANK, query="Summarise the feedback on system design.")
    print("[hindsight] reflect ok ->", ans.text[:120].replace("\n", " "))


if __name__ == "__main__":
    try:
        check_groq()
        check_hindsight()
    except Exception as e:
        print("FAILED:", type(e).__name__, e)
        sys.exit(1)
    print("All integrations working.")

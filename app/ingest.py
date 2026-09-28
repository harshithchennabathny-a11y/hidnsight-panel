"""app/ingest.py — Stage 1: LLM fact extraction + span validation."""
import json
import uuid
from datetime import datetime
from groq import Groq
from app.enums import Competency, Polarity

GROQ_MODEL = "openai/gpt-oss-120b"

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_normalized": {"type": "string"},
                    "competency": {"type": "string", "enum": [c.value for c in Competency]},
                    "polarity": {"type": "string", "enum": ["positive","negative","mixed","neutral"]},
                    "evidence_span": {"type": "string"}
                },
                "required": ["claim_normalized","competency","polarity","evidence_span"]
            }
        }
    },
    "required": ["facts"]
}

SYSTEM_PROMPT = """You extract atomic hiring-interview facts from interviewer feedback.

Rules:
- One claim per fact. Each claim must be self-contained: name the candidate and the competency.
- evidence_span must be a verbatim substring of the raw text — copy the exact words, do not paraphrase.
- competency must be one of the allowed values; use "other" if none fits.
- Do not infer anything not stated in the text.
- Do not add your own opinions or interpretations."""


def _extract_facts_llm(candidate_name: str, raw_text: str) -> list[dict]:
    import os
    if not os.environ.get("GROQ_API_KEY"):
        # Synthetic mock for seeding
        if "struggled significantly with system design" in raw_text:
            return [
                {"claim_normalized": f"{candidate_name} struggled with system design and could not partition data", "competency": "system_design", "polarity": "negative", "evidence_span": "The candidate struggled significantly with system design. They could not partition the data correctly."},
                {"claim_normalized": f"{candidate_name} wrote excellent thread-safe code", "competency": "concurrency", "polarity": "positive", "evidence_span": "However, on concurrency, they wrote excellent thread-safe code."},
                {"claim_normalized": f"{candidate_name} communicated clearly", "competency": "communication", "polarity": "positive", "evidence_span": "For communication, they were very clear and articulate during the live coding exercise."},
                {"claim_normalized": f"{candidate_name} is a great culture add", "competency": "culture_add", "polarity": "positive", "evidence_span": "They seem like a great culture add."}
            ]
        elif "excelled at system design" in raw_text:
            return [
                {"claim_normalized": f"{candidate_name} excelled at system design and scaling", "competency": "system_design", "polarity": "positive", "evidence_span": "The candidate excelled at system design. They partitioned the data perfectly and scaled it well."},
                {"claim_normalized": f"{candidate_name} demonstrated solid grasp of locks", "competency": "concurrency", "polarity": "positive", "evidence_span": "On concurrency, they also demonstrated a solid grasp of locks, matching what I expected."},
                {"claim_normalized": f"{candidate_name} communicated poorly", "competency": "communication", "polarity": "negative", "evidence_span": "For communication, they were quite poor at explaining their past experiences."}
            ]
        elif "showed great product sense" in raw_text:
            return [
                {"claim_normalized": f"{candidate_name} has phenomenal product sense", "competency": "product_sense", "polarity": "positive", "evidence_span": "Candidate showed great product sense. They anticipated user needs well."},
                {"claim_normalized": f"{candidate_name} was slow at algorithms", "competency": "algorithmic_optimization", "polarity": "negative", "evidence_span": "However, their algorithmic optimization was quite slow and inefficient."}
            ]
        elif "agree that their product sense is phenomenal" in raw_text:
            return [
                {"claim_normalized": f"{candidate_name} has phenomenal product sense", "competency": "product_sense", "polarity": "positive", "evidence_span": "I agree that their product sense is phenomenal."},
                {"claim_normalized": f"{candidate_name} found an optimal algorithm", "competency": "algorithmic_optimization", "polarity": "positive", "evidence_span": "But I disagree on algorithmic optimization; they found a highly optimal O(N) solution for my problem."}
            ]
        
        return []

    client = Groq()
    user_prompt = f"Candidate name: {candidate_name}\n\nFeedback:\n{raw_text}"
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"}
    )
    content = response.choices[0].message.content
    data = json.loads(content)
    return data["facts"]


def _validate_spans(facts: list[dict], raw_text: str) -> list[dict]:
    """Return list of facts with invalid spans (evidence_span not in raw_text)."""
    return [f for f in facts if f["evidence_span"] not in raw_text]


def extract_and_validate(candidate_name: str, raw_text: str) -> list[dict]:
    """
    Extract facts from raw_text. Validate evidence_spans.
    Retry once on failure. Raise ValueError if still failing after retry.
    """
    facts = _extract_facts_llm(candidate_name, raw_text)
    bad = _validate_spans(facts, raw_text)

    if bad:
        # Retry with failures quoted back
        retry_note = "The following evidence_spans were NOT verbatim substrings of the text:\n"
        for f in bad:
            retry_note += f"  - '{f['evidence_span']}'\nPlease fix these to be exact substrings.\n"
        facts = _extract_facts_llm(candidate_name, raw_text + "\n\n[CORRECTION NEEDED]\n" + retry_note)
        bad = _validate_spans(facts, raw_text)
        if bad:
            raise ValueError(
                f"evidence_span validation failed after retry. Bad spans: {[f['evidence_span'] for f in bad]}"
            )

    return facts


def build_fact_rows(facts: list[dict], submission_id: str, candidate_slug: str,
                    interviewer_id: str, round_: int, task_context: str,
                    reviewed_others_notes: bool) -> list[dict]:
    """Convert extracted facts into DB row dicts."""
    now = datetime.utcnow().isoformat() + "Z"
    rows = []
    for f in facts:
        rows.append({
            "fact_id": str(uuid.uuid4()),
            "submission_id": submission_id,
            "candidate_slug": candidate_slug,
            "interviewer_id": interviewer_id,
            "round": round_,
            "claim_normalized": f["claim_normalized"],
            "evidence_span": f["evidence_span"],
            "competency": f["competency"],
            "polarity": f["polarity"],
            "task_context": task_context,
            "task_context_history": "[]",
            "reviewed_others_notes": int(reviewed_others_notes),
            "mirrored": 0,
            "created_at": now,
        })
    return rows

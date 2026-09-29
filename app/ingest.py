"""app/ingest.py — Stage 1: LLM fact extraction + span validation.

Uses the real Groq client from app.config (no mock fallback).
Model name comes from app.config.GROQ_MODEL (R11).
Never fabricates output; raises on failure (R6).
"""
import json
import uuid
from datetime import datetime

from app.config import groq_client, GROQ_MODEL
from app.enums import Competency, Polarity

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_normalized": {"type": "string"},
                    "competency": {
                        "type": "string",
                        "enum": [c.value for c in Competency],
                    },
                    "polarity": {
                        "type": "string",
                        "enum": ["positive", "negative", "mixed", "neutral"],
                    },
                    "evidence_span": {"type": "string"},
                },
                "required": [
                    "claim_normalized",
                    "competency",
                    "polarity",
                    "evidence_span",
                ],
            },
        }
    },
    "required": ["facts"],
}

SYSTEM_PROMPT = """You extract atomic hiring-interview facts from interviewer feedback.

Return a JSON object with a single key "facts" whose value is an array of fact objects.
Each fact object MUST have exactly these four string fields:
  - "claim_normalized": a self-contained sentence naming the candidate and the competency
  - "competency": exactly one of the allowed values listed below
  - "polarity": exactly one of "positive", "negative", "mixed", "neutral"
  - "evidence_span": a verbatim substring of the raw feedback text (exact characters, no paraphrasing)

Allowed competency values: system_design, concurrency, algorithmic_optimization, communication, product_sense, culture_add, other

Rules:
- One claim per fact. Each claim must be self-contained: name the candidate and the competency.
- evidence_span must be a verbatim substring of the raw text — copy the exact words, do not paraphrase.
- competency must be one of the allowed values; use "other" if none fits.
- Do not infer anything not stated in the text.
- Do not add your own opinions or interpretations."""


# Common aliases some models use for our field names
_FIELD_ALIASES = {
    "claim": "claim_normalized",
    "normalized_claim": "claim_normalized",
    "claim_text": "claim_normalized",
    "statement": "claim_normalized",
    "span": "evidence_span",
    "evidence": "evidence_span",
    "quote": "evidence_span",
    "text_span": "evidence_span",
    "verbatim_span": "evidence_span",
    "skill": "competency",
    "category": "competency",
    "sentiment": "polarity",
    "type": "polarity",
}


def _normalize_fact_keys(fact: dict) -> dict:
    """Rename any aliased field names to canonical names."""
    normalized = {}
    for k, v in fact.items():
        canonical = _FIELD_ALIASES.get(k, k)
        normalized[canonical] = v
    return normalized


def _extract_facts_llm(candidate_name: str, raw_text: str) -> list[dict]:
    """Call Groq to extract facts. Raises on API failure (R6)."""
    client = groq_client()
    user_prompt = f"Candidate name: {candidate_name}\n\nFeedback:\n{raw_text}"
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    data = json.loads(content)
    raw_facts = data.get("facts", data.get("items", []))
    return [_normalize_fact_keys(f) for f in raw_facts]


def _validate_spans(facts: list[dict], raw_text: str) -> list[dict]:
    """Return list of facts with invalid spans (evidence_span not a substring of raw_text).
    
    LOOPHOLE FIX #6: Check case-insensitively first, then exact match.
    If the span exists case-insensitively but not exactly, attempt to find the
    correct-casing version in raw_text and correct the fact in-place.
    Only flag as invalid if the span is not present even case-insensitively.
    """
    raw_lower = raw_text.lower()
    bad = []
    for f in facts:
        span = f["evidence_span"]
        if span in raw_text:
            continue  # exact match — all good
        if span.lower() in raw_lower:
            # Case mismatch — find and fix the exact casing from raw_text
            idx = raw_lower.index(span.lower())
            f["evidence_span"] = raw_text[idx: idx + len(span)]
        else:
            bad.append(f)
    return bad


def extract_and_validate(candidate_name: str, raw_text: str) -> list[dict]:
    """
    Extract facts from raw_text. Validate evidence_spans.
    Retry once on failure with failing spans quoted back.
    Raises ValueError if still failing after one retry.
    Raises ConfigError / Groq error if the API call itself fails.
    """
    facts = _extract_facts_llm(candidate_name, raw_text)
    bad = _validate_spans(facts, raw_text)

    if bad:
        retry_note = "The following evidence_spans were NOT verbatim substrings of the text:\n"
        for f in bad:
            retry_note += f"  - '{f['evidence_span']}'\nPlease fix these to be exact substrings.\n"
        facts = _extract_facts_llm(
            candidate_name,
            raw_text + "\n\n[CORRECTION NEEDED]\n" + retry_note,
        )
        bad = _validate_spans(facts, raw_text)
        if bad:
            raise ValueError(
                f"evidence_span validation failed after retry. "
                f"Bad spans: {[f['evidence_span'] for f in bad]}"
            )

    return facts


def build_fact_rows(
    facts: list[dict],
    submission_id: str,
    candidate_slug: str,
    interviewer_id: str,
    round_: int,
    task_context: str,
    reviewed_others_notes: bool,
) -> list[dict]:
    """Convert extracted facts into DB row dicts."""
    now = datetime.utcnow().isoformat() + "Z"
    rows = []
    for f in facts:
        rows.append(
            {
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
            }
        )
    return rows

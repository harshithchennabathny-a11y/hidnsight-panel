import pytest
from unittest.mock import patch
from app.ingest import extract_and_validate, _validate_spans

RAW_TEXT = "The candidate showed excellent system design skills and poor communication ability."

def test_span_validator_pass():
    facts = [{"evidence_span": "excellent system design skills", "claim_normalized": "...", "competency": "system_design", "polarity": "positive"}]
    bad = _validate_spans(facts, RAW_TEXT)
    assert bad == []

def test_span_validator_fail():
    facts = [{"evidence_span": "great at coding", "claim_normalized": "...", "competency": "system_design", "polarity": "positive"}]
    bad = _validate_spans(facts, RAW_TEXT)
    assert len(bad) == 1

@patch("app.ingest._extract_facts_llm")
def test_extract_retries_on_bad_span(mock_llm):
    bad_fact = {"evidence_span": "DOES NOT EXIST IN TEXT", "claim_normalized": "...", "competency": "system_design", "polarity": "positive"}
    good_fact = {"evidence_span": "excellent system design skills", "claim_normalized": "...", "competency": "system_design", "polarity": "positive"}
    mock_llm.side_effect = [[bad_fact], [good_fact]]
    result = extract_and_validate("Alice", RAW_TEXT)
    assert mock_llm.call_count == 2
    assert result[0]["evidence_span"] == "excellent system design skills"

@patch("app.ingest._extract_facts_llm")
def test_extract_raises_after_two_failures(mock_llm):
    bad_fact = {"evidence_span": "NOT IN TEXT", "claim_normalized": "...", "competency": "system_design", "polarity": "positive"}
    mock_llm.return_value = [bad_fact]
    with pytest.raises(ValueError, match="validation failed after retry"):
        extract_and_validate("Alice", RAW_TEXT)
    assert mock_llm.call_count == 2

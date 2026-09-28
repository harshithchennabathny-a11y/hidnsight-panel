from unittest.mock import MagicMock, Mock, patch
import pytest

from app.synthesis import lint_text
from app.provenance import verdict_path_human_readable

# Groq SDK types — imported so spec= catches wrong field names at mock-build time.
from groq.types.chat.chat_completion import ChatCompletion, Choice
from groq.types.chat.chat_completion_message import ChatCompletionMessage

# Phrases that MUST fail lint
MUST_FAIL = [
    "Alice was right about the design",
    "Bob appears more thorough in his assessment",
    "Interviewer A seems more reliable",
    "Claim A is more accurate",
    "The panel should trust Bob's assessment",
    "Alice is more likely correct",
    "Bob showed stronger assessment skills",
    "We should hire the candidate",
]

# Phrases that MUST pass lint
MUST_PASS = [
    "Alice (round 1) described the design as lacking a scaling discussion.",
    "Bob (round 2) reported excellent system design with sharding proposed.",
    "The two assessments differ on the topic of scaling.",
]

def test_lint_fails_banned_phrases():
    for phrase in MUST_FAIL:
        violations = lint_text(phrase)
        assert violations, f"Expected lint to FAIL for: '{phrase}'"

def test_lint_passes_neutral_phrases():
    for phrase in MUST_PASS:
        violations = lint_text(phrase)
        assert not violations, f"Expected lint to PASS for: '{phrase}', got: {violations}"

def test_provenance_map_complete():
    keys = [
        ("stage2_sufficiency", "single_source"),
        ("stage2_sufficiency", "anchored_agreement_only"),
        ("stage2_5_context", "CONTEXT_SPLIT"),
        ("stage2_5_context", "COMPLEMENTARY"),
        ("stage3_rules", "CONTRADICTION"),
        ("stage3_rules", "COMPLEMENTARY"),
        ("stage4_llm", None),
    ]
    for verdict_path, ctx in keys:
        text = verdict_path_human_readable(verdict_path, ctx)
        assert isinstance(text, str) and len(text) > 10
        violations = lint_text(text)
        assert not violations, f"Provenance text for {verdict_path}/{ctx} failed lint: {violations}"


def test_groq_call_parameters_and_reasoning_effort():
    from app.synthesis import _groq_call

    mock_msg = Mock(spec=ChatCompletionMessage)
    mock_msg.content = '{"verdict": "CONTRADICTION"}'
    mock_choice = Mock(spec=Choice)
    mock_choice.message = mock_msg
    mock_choice.finish_reason = "stop"

    mock_completion = Mock(spec=ChatCompletion)
    mock_completion.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with patch("app.synthesis.groq_client", return_value=mock_client):
        result = _groq_call("system instruction", "user message")
        assert result == '{"verdict": "CONTRADICTION"}'
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] >= 1500
        assert call_kwargs.get("reasoning_effort") == "low"


def test_groq_call_raises_on_empty_content():
    import pytest
    from app.synthesis import _groq_call

    mock_msg = Mock(spec=ChatCompletionMessage)
    mock_msg.content = "   "
    mock_choice = Mock(spec=Choice)
    mock_choice.message = mock_msg
    mock_choice.finish_reason = "length"

    mock_completion = Mock(spec=ChatCompletion)
    mock_completion.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with patch("app.synthesis.groq_client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="empty content"):
            _groq_call("system instruction", "user message")

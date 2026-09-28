from app.synthesis import lint_text
from app.provenance import verdict_path_human_readable

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

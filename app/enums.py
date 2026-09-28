"""
app/enums.py — All enums for Panel.
Define once here, import everywhere. Do not redefine in other modules.
"""
from enum import Enum


class Competency(str, Enum):
    system_design = "system_design"
    concurrency = "concurrency"
    algorithmic_optimization = "algorithmic_optimization"
    communication = "communication"
    product_sense = "product_sense"
    culture_add = "culture_add"
    other = "other"


class TaskContext(str, Enum):
    whiteboard_design = "whiteboard_design"
    live_coding = "live_coding"
    take_home_review = "take_home_review"
    pair_programming = "pair_programming"
    behavioral = "behavioral"
    system_design_discussion = "system_design_discussion"
    other = "other"


class Polarity(str, Enum):
    positive = "positive"
    negative = "negative"
    mixed = "mixed"
    neutral = "neutral"


class Verdict(str, Enum):
    CONTRADICTION = "CONTRADICTION"
    CONDITIONAL_BOTH_APPLY = "CONDITIONAL_BOTH_APPLY"
    COMPLEMENTARY = "COMPLEMENTARY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class VerdictPath(str, Enum):
    stage2_sufficiency = "stage2_sufficiency"
    stage2_5_context = "stage2_5_context"
    stage3_rules = "stage3_rules"
    stage4_llm = "stage4_llm"


class DisagreementKind(str, Enum):
    CONTRADICTION = "CONTRADICTION"
    CONTEXT_SPLIT = "CONTEXT_SPLIT"


class LifecycleState(str, Enum):
    RAISED = "RAISED"
    PROBE_ASKED = "PROBE_ASKED"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    STILL_OPEN = "STILL_OPEN"


class ResolutionType(str, Enum):
    CONFIRMS_CLAIM_A = "CONFIRMS_CLAIM_A"
    CONFIRMS_CLAIM_B = "CONFIRMS_CLAIM_B"
    BOTH_HOLD_UNDER_DIFFERENT_CONTEXT = "BOTH_HOLD_UNDER_DIFFERENT_CONTEXT"
    NEW_INFORMATION_UNRESOLVED = "NEW_INFORMATION_UNRESOLVED"
    UNCLEAR = "UNCLEAR"


class CandidateStatus(str, Enum):
    open = "open"
    finalized = "finalized"


class SynthesisSource(str, Enum):
    llm = "llm"
    template = "template"

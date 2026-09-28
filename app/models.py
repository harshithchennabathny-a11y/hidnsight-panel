"""
app/models.py — Pydantic v2 output contract for Panel.

These models define the API response shapes exactly as specified in AGENTS.md
"Output contract" section. Do not add fields not defined there.

Key rule: primary_pair, signal_summary and disagreement_id are null for INSUFFICIENT_EVIDENCE.
There is no confidence_score anywhere.
"""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, field_validator
import re

from app.enums import (
    Competency,
    TaskContext,
    Polarity,
    Verdict,
    VerdictPath,
    DisagreementKind,
    LifecycleState,
    ResolutionType,
    CandidateStatus,
    SynthesisSource,
)

# ---------------------------------------------------------------------------
# Slug validation regex — used in request models
# ---------------------------------------------------------------------------
_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# ---------------------------------------------------------------------------
# Output models (API responses)
# ---------------------------------------------------------------------------

class FactOut(BaseModel):
    """One atomic fact as returned in API responses.

    claim_raw maps to evidence_span (verbatim substring of submission text).
    interviewer maps to interviewer_id.
    """
    fact_id: str
    claim_raw: str           # evidence_span verbatim
    claim_normalized: str
    interviewer: str         # interviewer_id
    round: int
    task_context: TaskContext
    reviewed_others_notes: bool
    polarity: Polarity


class SignalSummary(BaseModel):
    """Raw NLI/polarity diagnostics — never labeled as 'confidence'."""
    polarity_opposite: bool
    nli_contradiction_max: float | None


class PrimaryPair(BaseModel):
    """The highest-severity fact pair for a competency."""
    fact_a: FactOut
    fact_b: FactOut


class CompetencyAnalysis(BaseModel):
    """Per-competency evaluation result.

    primary_pair, signal_summary, disagreement_id are null for INSUFFICIENT_EVIDENCE.
    """
    competency: Competency
    independent_source_count: int
    verdict: Verdict
    insufficiency_reason: str | None       # "single_source" | "anchored_agreement_only" | None
    verdict_path: VerdictPath
    verdict_path_human_readable: str       # from static provenance map, never LLM-written
    signal_summary: SignalSummary | None   # null for INSUFFICIENT_EVIDENCE
    anchored_dissent: bool
    pair_count: int
    primary_pair: PrimaryPair | None       # null for INSUFFICIENT_EVIDENCE
    disagreement_id: str | None            # null for INSUFFICIENT_EVIDENCE
    lifecycle_state: LifecycleState | None # null if no disagreement
    synthesis_rationale: str
    recommended_follow_up: str | None


class OpenDisagreementSummary(BaseModel):
    """Brief summary of an open disagreement for the evaluation response."""
    disagreement_id: str
    kind: DisagreementKind
    competency: Competency
    state: LifecycleState
    raised_at: str                         # ISO-8601


class EvaluationResponse(BaseModel):
    """Full output contract for GET /candidates/{slug}/evaluation."""
    candidate_slug: str
    display_name: str = ""               # populated from candidates table for UI header
    status: CandidateStatus = "open"     # populated from candidates table for UI chip
    evaluated_at: str                      # ISO-8601
    briefing_summary: str
    synthesis_source: SynthesisSource
    competency_analyses: list[CompetencyAnalysis]
    open_disagreements_summary: list[OpenDisagreementSummary]

    @property
    def open_contradictions_summary(self) -> list[OpenDisagreementSummary]:
        """Alias for open_disagreements_summary matching legacy specification terminology."""
        return self.open_disagreements_summary


class CandidateListItem(BaseModel):
    """Item in GET /candidates response."""
    slug: str
    display_name: str
    status: CandidateStatus
    round_count: int
    open_disagreement_count: int


class DisagreementDetail(BaseModel):
    """Full disagreement object for GET /candidates/{slug}/disagreements."""
    disagreement_id: str
    candidate_slug: str
    competency: Competency
    kind: DisagreementKind
    interviewer_a_id: str
    interviewer_b_id: str
    fact_a: FactOut
    fact_b: FactOut
    state: LifecycleState
    follow_up: str | None
    created_at: str
    updated_at: str
    transitions: list[dict[str, Any]]      # append-only log rows


class BriefingResponse(BaseModel):
    """Response for GET /candidates/{slug}/briefing?for_round=N."""
    for_round: int
    overview: str | None                   # None if no prior facts or lint failed twice
    synthesis_source: SynthesisSource
    earlier_findings: list[dict[str, Any]]
    open_disagreements: list[dict[str, Any]]
    insufficient_competencies: list[str]
    generic: bool = False                  # True when no prior facts exist at all


class FinalizeResponse(BaseModel):
    """Response for POST /candidates/{slug}/finalize."""
    candidate_slug: str
    finalized_at: str
    disagreements: list[dict[str, Any]]
    still_open_count: int
    resolved_count: int


# ---------------------------------------------------------------------------
# Request models (API inputs)
# ---------------------------------------------------------------------------

class SubmissionRequest(BaseModel):
    """POST /submissions request body."""
    candidate_slug: str
    candidate_name: str
    interviewer_id: str
    interviewer_name: str
    round: int
    task_context: TaskContext
    reviewed_others_notes: bool
    feedback_text: str

    @field_validator("candidate_slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("candidate_slug must match ^[a-z0-9]+(-[a-z0-9]+)*$")
        return v

    @field_validator("round")
    @classmethod
    def round_range(cls, v: int) -> int:
        if not 1 <= v <= 10:
            raise ValueError("round must be between 1 and 10")
        return v

    @field_validator("feedback_text")
    @classmethod
    def text_length(cls, v: str) -> str:
        if not 20 <= len(v) <= 4000:
            raise ValueError("feedback_text must be 20–4000 characters")
        return v

    @field_validator("interviewer_id", "interviewer_name", "candidate_name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be empty")
        return v


class ResolutionRequest(BaseModel):
    """POST /disagreements/{id}/resolution request body."""
    resolution_type: ResolutionType
    note: str
    context_a: TaskContext | None = None   # required for BOTH_HOLD_UNDER_DIFFERENT_CONTEXT
    context_b: TaskContext | None = None   # required for BOTH_HOLD_UNDER_DIFFERENT_CONTEXT

    @field_validator("note")
    @classmethod
    def note_length(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("note must be at least 10 characters")
        return v


# ---------------------------------------------------------------------------
# Helper: convert a facts DB row to FactOut
# ---------------------------------------------------------------------------

def fact_row_to_out(row: dict) -> FactOut:
    """Convert a SQLite facts row (dict or sqlite3.Row) to FactOut."""
    if hasattr(row, "keys"):
        row = dict(row)
    return FactOut(
        fact_id=row["fact_id"],
        claim_raw=row["evidence_span"],
        claim_normalized=row["claim_normalized"],
        interviewer=row["interviewer_id"],
        round=row["round"],
        task_context=TaskContext(row["task_context"]),
        reviewed_others_notes=bool(row["reviewed_others_notes"]),
        polarity=Polarity(row["polarity"]),
    )

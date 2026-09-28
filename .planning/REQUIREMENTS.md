# REQUIREMENTS.md — Panel

## Functional Requirements

### FR-1: Submission
- FR-1.1 Accept POST /submissions with: candidate_slug, candidate_name, interviewer_id, interviewer_name, round (1–10), task_context (enum), reviewed_others_notes (bool), feedback_text (20–4000 chars)
- FR-1.2 Validate slug matches `^[a-z0-9]+(-[a-z0-9]+)*$`
- FR-1.3 Auto-create candidate on first submission for a slug
- FR-1.4 Reject duplicate (candidate_slug, interviewer_id, round) with 409
- FR-1.5 Reject submission for finalized candidate with 409

### FR-2: Fact Extraction (Stage 1)
- FR-2.1 One Groq LLM call extracts a list of facts: claim_normalized, competency, polarity, evidence_span
- FR-2.2 Every evidence_span must be a verbatim substring of raw_text (code-validated)
- FR-2.3 On span validation failure: retry once with failing spans quoted back; 502 on second failure
- FR-2.4 Store submission + facts in one SQLite transaction
- FR-2.5 Mirror each fact to Hindsight bank `hiring-candidate-{slug}` with tag `type:fact`
- FR-2.6 If Hindsight mirror fails: return 502, keep data in SQLite, set mirrored=false

### FR-3: Verdict Pipeline
- FR-3.1 Stage 2 (pure code): sufficiency gate — INSUFFICIENT_EVIDENCE/single_source if <2 distinct interviewers
- FR-3.2 Stage 2 (pure code): INSUFFICIENT_EVIDENCE/anchored_agreement_only if all pairs anchored + same polarity
- FR-3.3 Stage 2 (pure code): anchored+opposite-polarity pairs are eligible with anchored_dissent=true
- FR-3.4 Stage 2.5 (pure code): different context + opposite polarity → CONTEXT_SPLIT
- FR-3.5 Stage 2.5 (pure code): different context + same polarity → COMPLEMENTARY
- FR-3.6 Stage 3 (NLI + code): decision table produces CONTRADICTION, COMPLEMENTARY, or escalate
- FR-3.7 Stage 4 (LLM): escalated pairs adjudicated to one of 3 verdicts + rationale
- FR-3.8 All pair verdicts stored; already-stored pairs never re-run (idempotent)
- FR-3.9 Competency verdict = highest severity across pairs (CONTRADICTION > CONDITIONAL_BOTH_APPLY > COMPLEMENTARY)
- FR-3.10 Cap at 15 pairs per competency; keep most recent rounds

### FR-4: Disagreements
- FR-4.1 Every CONTRADICTION or CONTEXT_SPLIT pair creates a disagreement row
- FR-4.2 One disagreement per (candidate_slug, competency, interviewer_a_id, interviewer_b_id, kind)
- FR-4.3 Disagreement points at highest-severity pair; not replaced on subsequent evaluations
- FR-4.4 Initial state: RAISED; follow-up question generated at creation
- FR-4.5 Transition row written for every state change (append-only)
- FR-4.6 Hindsight retain for every transition (tag: type:transition)

### FR-5: Lifecycle
- FR-5.1 Allowed transitions: RAISED→{PROBE_ASKED,RESOLVED,ESCALATED}, PROBE_ASKED→{RESOLVED,ESCALATED}, ESCALATED→{PROBE_ASKED,RESOLVED}
- FR-5.2 RESOLVED and STILL_OPEN are terminal
- FR-5.3 Invalid transition returns 409
- FR-5.4 Resolution types and their state outcomes per AGENTS.md
- FR-5.5 BOTH_HOLD_UNDER_DIFFERENT_CONTEXT: requires context_a+context_b, retro-tags both facts, keeps task_context_history
- FR-5.6 Resolution note retained to Hindsight as type:resolution with disagreement_id

### FR-6: Briefing
- FR-6.1 GET /candidates/{slug}/briefing?for_round=N returns facts from rounds < N only
- FR-6.2 Structure built by code: earlier findings, open disagreements, insufficient competencies
- FR-6.3 No earlier facts → generic template naming all 6 competencies
- FR-6.4 Optional LLM overview (3–5 sentences) via Hindsight reflect or Groq, with lint
- FR-6.5 Lint fails twice → omit overview, show structured sections, synthesis_source="template"

### FR-7: Finalize
- FR-7.1 POST /candidates/{slug}/finalize sets status=finalized, moves all non-RESOLVED to STILL_OPEN
- FR-7.2 Returns final summary: all disagreements with states, verdicts per competency, insufficient list
- FR-7.3 After finalization: 409 on any new submission or resolution

### FR-8: API
- FR-8.1 GET /candidates → list with slug, display_name, status, round_count, open_disagreement_count
- FR-8.2 GET /candidates/{slug}/evaluation → full output contract (assembled from SQLite)
- FR-8.3 GET /candidates/{slug}/disagreements → all disagreements with both facts + transitions
- FR-8.4 All validation errors: 400; not found: 404; conflicts: 409; external failures: 502

## Non-functional Requirements

### NFR-1: Anti-adjudication
- No generated text may state or imply one interviewer is more right, credible, or reliable
- Lint guard enforced on all LLM outputs and templates
- Banned phrases list per AGENTS.md Section 10

### NFR-2: Transparency
- Every verdict shows verdict_path_human_readable (static template, never LLM-written)
- NLI probabilities shown as raw signals only, never labeled as confidence

### NFR-3: Idempotency
- evaluate_candidate() re-run never duplicates pair_verdicts or disagreements
- create_disagreement() is idempotent on its unique key

### NFR-4: Testability
- `pytest -m "not live"` passes offline (no Groq, Hindsight, or NLI calls)
- Live tests marked with @pytest.mark.live

### NFR-5: UI Fairness
- Claim A and Claim B rendered identically (size, weight, color)
- Verdict colors only on verdict badge, never on claims or interviewer names

### NFR-6: Data
- Synthetic data only; disclosed in DEMO_NOTES.md
- No real candidate data ever stored

## Out of Scope
- Auth, login, accounts
- Overall candidate score or ranking
- Hire/no-hire recommendation
- Fact editing
- Email/calendar integration
- Resume parsing
- Multi-candidate comparison
- Production deployment hardening
- GET /calibration (Part 10 only, deferred)

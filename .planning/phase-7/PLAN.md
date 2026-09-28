---
phase: 7
title: API and React/Tailwind UI
status: not_started
wave_count: 3
estimated_minutes: 90
depends_on: [phase-6]
---

# Phase 7 Plan — API and React/Tailwind UI

## Goal
All 8 FastAPI endpoints wired up + a three-tab React/Tailwind UI a judge can click through. Path line always visible. ClaimPair always equal.

## Pre-conditions
- Phases 0–6 complete
- `frontend/` scaffolded with Vite + React + Tailwind (Phase 0)
- All backend modules (ingest, gates, classify, synthesis, provenance, lifecycle) complete

---

## Wave 1 — FastAPI endpoints (`app/main.py`)

### Task 7.1 — App setup + CORS

```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI(title="Panel")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("VITE_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Task 7.2 — `GET /candidates`

```python
@app.get("/candidates", response_model=list[CandidateListItem])
def list_candidates():
    conn = get_connection()
    rows = conn.execute("SELECT slug, display_name, status FROM candidates").fetchall()
    result = []
    for r in rows:
        round_count = conn.execute(
            "SELECT COUNT(DISTINCT round) FROM submissions WHERE candidate_slug=?", (r["slug"],)
        ).fetchone()[0]
        open_count = conn.execute(
            "SELECT COUNT(*) FROM disagreements WHERE candidate_slug=? AND state NOT IN ('RESOLVED','STILL_OPEN')",
            (r["slug"],)
        ).fetchone()[0]
        result.append(CandidateListItem(
            slug=r["slug"], display_name=r["display_name"], status=r["status"],
            round_count=round_count, open_disagreement_count=open_count
        ))
    return result
```

### Task 7.3 — `POST /submissions`

Processing order exactly per APPLICATION_SPEC.md §6.1:
1. Validate (slug regex, round 1–10, task_context enum, text 20–4000, all fields present) → 400
2. Check candidate not finalized → 409
3. Check no duplicate (slug, interviewer_id, round) → 409
4. Create candidate if new
5. `extract_and_validate()` → on failure raise 502
6. Insert submission + facts in one transaction
7. Mirror each fact to Hindsight → on failure 502 (data stays in SQLite)
8. `evaluate_candidate(slug, conn)` for touched competencies
9. Return `{submission_id, facts: [FactOut], evaluation: [CompetencyAnalysis]}`

```python
@app.post("/submissions")
def post_submission(req: SubmissionRequest):
    # Validation
    if not SLUG_RE.match(req.candidate_slug):
        raise HTTPException(400, detail={"error": "candidate_slug must match ^[a-z0-9]+(-[a-z0-9]+)*$"})
    if not 1 <= req.round <= 10:
        raise HTTPException(400, detail={"error": "round must be 1–10"})
    if not 20 <= len(req.feedback_text) <= 4000:
        raise HTTPException(400, detail={"error": "feedback_text must be 20–4000 characters"})

    conn = get_connection()

    candidate = conn.execute("SELECT status FROM candidates WHERE slug=?", (req.candidate_slug,)).fetchone()
    if candidate and candidate["status"] == "finalized":
        raise HTTPException(409, detail={"error": "Candidate is finalized"})

    dup = conn.execute(
        "SELECT 1 FROM submissions WHERE candidate_slug=? AND interviewer_id=? AND round=?",
        (req.candidate_slug, req.interviewer_id, req.round)
    ).fetchone()
    if dup:
        raise HTTPException(409, detail={"error": f"Submission already exists for {req.interviewer_id} round {req.round}"})

    # Create candidate if new
    if not candidate:
        now = datetime.utcnow().isoformat() + "Z"
        conn.execute("INSERT INTO candidates (slug,display_name,status,created_at) VALUES (?,?,?,?)",
                     (req.candidate_slug, req.candidate_name, "open", now))
        conn.commit()

    # Extract + validate facts
    try:
        raw_facts = extract_and_validate(req.candidate_name, req.feedback_text)
    except ValueError as e:
        raise HTTPException(502, detail={"error": f"Fact extraction failed: {e}"})

    # Build + insert rows
    submission_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    fact_rows = build_fact_rows(raw_facts, submission_id, req.candidate_slug,
                                 req.interviewer_id, req.round,
                                 req.task_context.value, req.reviewed_others_notes)
    with conn:
        conn.execute(
            "INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)",
            (submission_id, req.candidate_slug, req.interviewer_id, req.interviewer_name,
             req.round, req.task_context.value, int(req.reviewed_others_notes),
             req.feedback_text, now)
        )
        for f in fact_rows:
            conn.execute(
                "INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f["fact_id"], f["submission_id"], f["candidate_slug"], f["interviewer_id"],
                 f["round"], f["claim_normalized"], f["evidence_span"], f["competency"],
                 f["polarity"], f["task_context"], f["task_context_history"],
                 f["reviewed_others_notes"], 0, f["created_at"])
            )

    # Mirror to Hindsight
    unmirrored = []
    for f in fact_rows:
        try:
            retain_fact(f, req.candidate_slug)
            conn.execute("UPDATE facts SET mirrored=1 WHERE fact_id=?", (f["fact_id"],))
            conn.commit()
        except Exception:
            unmirrored.append(f["fact_id"])
    if unmirrored:
        raise HTTPException(502, detail={"error": "Hindsight mirror failed", "submission_id": submission_id, "unmirrored_fact_ids": unmirrored})

    # Evaluate
    evaluation = evaluate_candidate(req.candidate_slug, conn)

    return {
        "submission_id": submission_id,
        "facts": [fact_to_out(f) for f in fact_rows],
        "evaluation": evaluation["competency_analyses"],
    }
```

### Task 7.4 — Remaining endpoints

```python
@app.get("/candidates/{slug}/evaluation")
def get_evaluation(slug: str):
    conn = get_connection()
    _check_candidate_exists(slug, conn)
    return evaluate_candidate(slug, conn)

@app.get("/candidates/{slug}/briefing")
def get_briefing(slug: str, for_round: int):
    conn = get_connection()
    _check_candidate_exists(slug, conn)
    return briefing(slug, for_round, conn)

@app.get("/candidates/{slug}/disagreements")
def get_disagreements(slug: str):
    conn = get_connection()
    _check_candidate_exists(slug, conn)
    rows = conn.execute("SELECT * FROM disagreements WHERE candidate_slug=?", (slug,)).fetchall()
    result = []
    for d in rows:
        transitions = conn.execute(
            "SELECT * FROM transitions WHERE disagreement_id=? ORDER BY created_at",
            (d["disagreement_id"],)
        ).fetchall()
        fact_a = conn.execute("SELECT * FROM facts WHERE fact_id=?", (d["fact_a_id"],)).fetchone()
        fact_b = conn.execute("SELECT * FROM facts WHERE fact_id=?", (d["fact_b_id"],)).fetchone()
        result.append({
            **dict(d),
            "fact_a": fact_to_out(dict(fact_a)),
            "fact_b": fact_to_out(dict(fact_b)),
            "transitions": [dict(t) for t in transitions],
        })
    return result

@app.post("/disagreements/{disagreement_id}/probe-asked")
def probe_asked(disagreement_id: str):
    conn = get_connection()
    try:
        return mark_probe_asked(disagreement_id, conn)
    except InvalidTransition as e:
        raise HTTPException(409, detail={"error": str(e)})
    except KeyError:
        raise HTTPException(404, detail={"error": "Disagreement not found"})

@app.post("/disagreements/{disagreement_id}/resolution")
def post_resolution(disagreement_id: str, req: ResolutionRequest):
    if len(req.note) < 10:
        raise HTTPException(400, detail={"error": "note must be at least 10 characters"})
    conn = get_connection()
    try:
        return submit_resolution(
            disagreement_id, req.resolution_type.value, req.note,
            req.context_a.value if req.context_a else None,
            req.context_b.value if req.context_b else None,
            conn
        )
    except InvalidTransition as e:
        raise HTTPException(409, detail={"error": str(e)})
    except ValueError as e:
        raise HTTPException(400, detail={"error": str(e)})
    except KeyError:
        raise HTTPException(404, detail={"error": "Disagreement not found"})

@app.post("/candidates/{slug}/finalize")
def finalize_candidate(slug: str):
    conn = get_connection()
    try:
        return finalize(slug, conn)
    except ValueError as e:
        raise HTTPException(409, detail={"error": str(e)})
```

---

## Wave 2 — React component structure (`frontend/src/`)

### Task 7.5 — File layout

```
frontend/src/
  App.jsx                  # top bar + candidate selector + 3 tabs
  api.js                   # all fetch calls, base URL from VITE_API_URL
  components/
    SubmissionForm.jsx
    CandidateView.jsx
    BriefingPanel.jsx
    CompetencyCard.jsx
    ClaimPair.jsx           # ← UI fairness enforced here
    PathBadge.jsx
    VerdictBadge.jsx
    DisagreementsPanel.jsx
    ProvenanceTimeline.jsx
    ResolutionForm.jsx
    LifecycleChip.jsx
    LoadingSpinner.jsx
    ErrorMessage.jsx
```

### Task 7.6 — `api.js`

```js
const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const handle = async (res) => {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  return res.json();
};

export const getCandidates = () => fetch(`${BASE}/candidates`).then(handle);
export const postSubmission = (body) =>
  fetch(`${BASE}/submissions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(handle);
export const getEvaluation = (slug) => fetch(`${BASE}/candidates/${slug}/evaluation`).then(handle);
export const getBriefing = (slug, forRound) => fetch(`${BASE}/candidates/${slug}/briefing?for_round=${forRound}`).then(handle);
export const getDisagreements = (slug) => fetch(`${BASE}/candidates/${slug}/disagreements`).then(handle);
export const postProbeAsked = (id) => fetch(`${BASE}/disagreements/${id}/probe-asked`, { method: 'POST' }).then(handle);
export const postResolution = (id, body) =>
  fetch(`${BASE}/disagreements/${id}/resolution`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(handle);
export const postFinalize = (slug) => fetch(`${BASE}/candidates/${slug}/finalize`, { method: 'POST' }).then(handle);
```

### Task 7.7 — `ClaimPair.jsx` (UI fairness — both sides identical)

```jsx
// ClaimPair.jsx
// RULE: Both columns MUST be identical in size, weight, and color.
// Verdict colors are NEVER applied here.
export default function ClaimPair({ factA, factB }) {
  return (
    <div className="grid grid-cols-2 gap-4 mt-3">
      <ClaimColumn label="Claim A" fact={factA} />
      <ClaimColumn label="Claim B" fact={factB} />
    </div>
  );
}

function ClaimColumn({ label, fact }) {
  return (
    // Identical className on both — do NOT vary by label
    <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
      <p className="text-xs font-semibold text-gray-500 uppercase mb-2">{label}</p>
      <blockquote className="text-sm text-gray-800 italic mb-3">
        "{fact.claim_raw}"
      </blockquote>
      <p className="text-xs text-gray-500">
        {fact.interviewer} · Round {fact.round} · {fact.task_context.replace(/_/g, ' ')}
      </p>
    </div>
  );
}
```

### Task 7.8 — `CompetencyCard.jsx`

Shows all required elements from APPLICATION_SPEC.md §7.2:
1. Competency name + VerdictBadge (color ONLY on badge)
2. PathBadge (always visible, never tooltip)
3. "Independent sources: N"
4. ClaimPair (if not INSUFFICIENT_EVIDENCE)
5. anchored_dissent note
6. "N pairs compared. The pair shown is the highest-severity one."
7. Rationale + follow-up
8. LifecycleChip
9. Diagnostics line (nli_contradiction_max, polarity_opposite — labeled as raw signals)

```jsx
export default function CompetencyCard({ analysis }) {
  const isInsufficient = analysis.verdict === 'INSUFFICIENT_EVIDENCE';

  return (
    <div className="border rounded-xl p-5 mb-4 bg-white shadow-sm">
      {/* 1. Header */}
      <div className="flex items-center gap-3 mb-1">
        <h3 className="font-semibold text-gray-900 capitalize">
          {analysis.competency.replace(/_/g, ' ')}
        </h3>
        <VerdictBadge verdict={analysis.verdict} />
        {analysis.lifecycle_state && <LifecycleChip state={analysis.lifecycle_state} />}
      </div>

      {/* 2. Path line — always visible */}
      <p className="text-xs text-gray-500 mb-3">{analysis.verdict_path_human_readable}</p>

      {/* 3. Independent sources */}
      <p className="text-xs text-gray-600 mb-3">
        Independent sources: {analysis.independent_source_count}
      </p>

      {isInsufficient ? (
        <p className="text-sm text-gray-600">{insufficiencyText(analysis.insufficiency_reason)}</p>
      ) : (
        <>
          {/* 4. Claim pair */}
          {analysis.primary_pair && (
            <ClaimPair factA={analysis.primary_pair.fact_a} factB={analysis.primary_pair.fact_b} />
          )}

          {/* 5. Anchored dissent note */}
          {analysis.anchored_dissent && (
            <p className="text-xs text-amber-700 mt-2">
              One of these assessments was written after reading the other interviewer's notes.
            </p>
          )}

          {/* 6. Pair count */}
          <p className="text-xs text-gray-400 mt-2">
            {analysis.pair_count} pairs compared. The pair shown is the highest-severity one.
          </p>

          {/* 7. Rationale + follow-up */}
          {analysis.synthesis_rationale && (
            <p className="text-sm text-gray-700 mt-3">{analysis.synthesis_rationale}</p>
          )}
          {analysis.recommended_follow_up && (
            <div className="mt-2 p-3 bg-blue-50 rounded text-sm text-blue-800">
              <span className="font-medium">Suggested follow-up: </span>
              {analysis.recommended_follow_up}
            </div>
          )}

          {/* 9. Diagnostics */}
          {analysis.signal_summary && (
            <p className="text-xs text-gray-400 mt-3">
              Raw signals — NLI contradiction score: {analysis.signal_summary.nli_contradiction_max?.toFixed(3) ?? 'n/a'} ·
              Opposite polarity: {analysis.signal_summary.polarity_opposite ? 'yes' : 'no'}
            </p>
          )}
        </>
      )}
    </div>
  );
}
```

### Task 7.9 — `VerdictBadge.jsx` — color ONLY here

```jsx
const COLORS = {
  CONTRADICTION:        'bg-red-100 text-red-800',
  CONDITIONAL_BOTH_APPLY: 'bg-yellow-100 text-yellow-800',
  COMPLEMENTARY:        'bg-green-100 text-green-800',
  INSUFFICIENT_EVIDENCE: 'bg-gray-100 text-gray-600',
};
const LABELS = {
  CONTRADICTION:        'Contradiction',
  CONDITIONAL_BOTH_APPLY: 'Both apply (conditional)',
  COMPLEMENTARY:        'Complementary',
  INSUFFICIENT_EVIDENCE: 'Insufficient evidence',
};

export default function VerdictBadge({ verdict }) {
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${COLORS[verdict]}`}>
      {LABELS[verdict]}
    </span>
  );
}
```

### Task 7.10 — `ProvenanceTimeline.jsx`

Built from the `transitions` array (from `GET /candidates/{slug}/disagreements`):

```jsx
export default function ProvenanceTimeline({ transitions, verdictPathHumanReadable }) {
  return (
    <div className="mt-3">
      <p className="text-xs text-gray-500 mb-2 font-medium">Path: {verdictPathHumanReadable}</p>
      <ol className="border-l border-gray-200 ml-2">
        {transitions.map((t, i) => (
          <li key={i} className="ml-4 mb-3 relative">
            <span className="absolute -left-6 mt-0.5 w-3 h-3 rounded-full bg-gray-300 border-2 border-white" />
            <p className="text-xs font-semibold text-gray-700">{t.to_state}</p>
            <p className="text-xs text-gray-400">{new Date(t.created_at).toLocaleString()}</p>
            {t.note && <p className="text-xs text-gray-600 mt-0.5">{t.note}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}
```

### Task 7.11 — `ResolutionForm.jsx`

```jsx
const RESOLUTION_LABELS = {
  CONFIRMS_CLAIM_A: 'The follow-up response is consistent with Claim A',
  CONFIRMS_CLAIM_B: 'The follow-up response is consistent with Claim B',
  BOTH_HOLD_UNDER_DIFFERENT_CONTEXT: 'Both claims hold, under different conditions',
  NEW_INFORMATION_UNRESOLVED: 'New information came up that is not yet resolved',
  UNCLEAR: 'The response did not clearly settle it',
};

const TASK_CONTEXT_LABELS = {
  whiteboard_design: 'Whiteboard Design',
  live_coding: 'Live Coding',
  take_home_review: 'Take-Home Review',
  pair_programming: 'Pair Programming',
  behavioral: 'Behavioral',
  system_design_discussion: 'System Design Discussion',
  other: 'Other',
};

export default function ResolutionForm({ disagreementId, onResolved }) {
  const [type, setType] = useState('');
  const [note, setNote] = useState('');
  const [ctxA, setCtxA] = useState('');
  const [ctxB, setCtxB] = useState('');
  const [error, setError] = useState(null);

  const needsContexts = type === 'BOTH_HOLD_UNDER_DIFFERENT_CONTEXT';

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (note.length < 10) { setError('Notes must be at least 10 characters'); return; }
    try {
      const body = { resolution_type: type, note };
      if (needsContexts) { body.context_a = ctxA; body.context_b = ctxB; }
      const updated = await postResolution(disagreementId, body);
      onResolved(updated);
    } catch (err) { setError(err.message); }
  };

  return (
    <form onSubmit={handleSubmit} className="mt-4 space-y-3">
      <label className="block text-sm font-medium text-gray-700">
        What happened when the follow-up was asked?
        <select value={type} onChange={e => setType(e.target.value)} required
          className="mt-1 block w-full border border-gray-300 rounded-md p-2 text-sm">
          <option value="">Select…</option>
          {Object.entries(RESOLUTION_LABELS).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </label>

      {needsContexts && (
        <div className="grid grid-cols-2 gap-3">
          <ContextSelect label="Context for Claim A" value={ctxA} onChange={setCtxA} />
          <ContextSelect label="Context for Claim B" value={ctxB} onChange={setCtxB} />
        </div>
      )}

      <label className="block text-sm font-medium text-gray-700">
        Notes
        <textarea value={note} onChange={e => setNote(e.target.value)} required minLength={10} rows={3}
          className="mt-1 block w-full border border-gray-300 rounded-md p-2 text-sm" />
      </label>

      {error && <p className="text-sm text-red-600">{error}</p>}
      <button type="submit" className="px-4 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700">
        Record resolution
      </button>
    </form>
  );
}
```

### Task 7.12 — `SubmissionForm.jsx`

Fields in exact order from APPLICATION_SPEC.md §7.1:
1. Candidate name (text) + Candidate ID (slug, auto-filled, editable, validated)
2. Your ID (text) + Your name (text)
3. Round (number 1–10)
4. Task context (dropdown)
5. Checkbox: "I read other interviewers' notes..."
6. Feedback textarea (20–4000, live counter)

On success: show extracted facts list with competency, polarity, **highlighted evidence span**.

### Task 7.13 — `DisagreementsPanel.jsx`

- Sorted: unresolved first
- Each row: kind chip, competency, LifecycleChip, raised date — expand on click
- Expanded: ProvenanceTimeline + ClaimPair (identical styling) + follow-up question
- Buttons per state: "Mark probe asked" / "Record resolution"
- Finalize button at top with confirmation dialog:
  > "Finalizing locks this candidate. Disagreements that are not resolved will be recorded as Still open."

---

## Wave 3 — Integration wiring

### Task 7.14 — `App.jsx`

```jsx
export default function App() {
  const [candidates, setCandidates] = useState([]);
  const [selectedSlug, setSelectedSlug] = useState('');
  const [activeTab, setActiveTab] = useState('submit');

  useEffect(() => {
    getCandidates().then(setCandidates).catch(console.error);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar */}
      <header className="bg-white border-b px-6 py-3 flex items-center gap-4">
        <h1 className="text-lg font-bold text-gray-900">Panel</h1>
        <select value={selectedSlug} onChange={e => setSelectedSlug(e.target.value)}
          className="border border-gray-300 rounded px-3 py-1 text-sm">
          <option value="">Select candidate…</option>
          {candidates.map(c => (
            <option key={c.slug} value={c.slug}>{c.display_name}</option>
          ))}
        </select>
      </header>

      {/* Tabs */}
      <nav className="border-b bg-white px-6">
        {['submit','candidate','disagreements'].map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={`px-4 py-3 text-sm font-medium capitalize border-b-2 mr-2
              ${activeTab === tab ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500'}`}>
            {tab}
          </button>
        ))}
      </nav>

      {/* Tab content */}
      <main className="max-w-4xl mx-auto px-6 py-6">
        {activeTab === 'submit' && <SubmissionForm onSuccess={() => getCandidates().then(setCandidates)} />}
        {activeTab === 'candidate' && selectedSlug && <CandidateView slug={selectedSlug} />}
        {activeTab === 'disagreements' && selectedSlug && <DisagreementsPanel slug={selectedSlug} />}
      </main>
    </div>
  );
}
```

---

## Acceptance Verification

| Check | How |
|---|---|
| Submit two conflicting feedbacks | Browser → Submit tab → two submissions same competency opposite polarity |
| CONTRADICTION card shows path line | Candidate tab → CompetencyCard has path text below badge |
| Resolve disagreement | Disagreements tab → Record resolution → state chip updates |
| No page reload needed | State updates via React state, no full reload |
| ClaimPair columns identical | Inspect DOM — both divs same className |
| Verdict color only on badge | No color class on ClaimColumn or interviewer name elements |
| Errors shown verbatim | Trigger a 400 → ErrorMessage shows exact API error text |

---
phase: 8
title: Seed Data, End-to-End Run, Demo Notes
status: not_started
wave_count: 2
estimated_minutes: 45
depends_on: [phase-7]
---

# Phase 8 Plan — Seed Data, End-to-End Run, Demo Notes

## Goal
Repeatable demo that shows all four verdicts, both disagreement kinds, the memory arc (briefing evolution), and Candidate B's anchored cases.

## Pre-conditions
- Phase 7 complete (all endpoints + UI working)
- Backend running (`uvicorn app.main:app`)

---

## Wave 1 — `scripts/seed.py`

### Task 8.1 — Candidate A design

**Slug:** `alex-chen` · **Display name:** "Alex Chen" · **Interviewers:** `diana`, `priya`, `sam`

Competency coverage (all four verdicts):

| Competency | Interviewers | Context | Polarity | Expected Verdict | Kind |
|---|---|---|---|---|---|
| `system_design` | diana (R1) + priya (R2) | both `whiteboard_design` | negative + positive | CONTRADICTION | CONTRADICTION |
| `concurrency` | diana (R1) + priya (R2) | both `live_coding` | positive + positive | COMPLEMENTARY | — |
| `communication` | diana (R1, `live_coding`) + sam (R3, `behavioral`) | different | negative + positive | CONDITIONAL_BOTH_APPLY | CONTEXT_SPLIT |
| `culture_add` | sam only (R3) | `behavioral` | positive | INSUFFICIENT_EVIDENCE | single_source |

**Round 3** (Sam) also includes a debrief transcript and a resolution for the `system_design` disagreement.

### Task 8.2 — Synthetic feedback texts for Candidate A

```python
CANDIDATE_A = {
    "slug": "alex-chen",
    "name": "Alex Chen",
}

SUBMISSIONS_A = [
    {
        "interviewer_id": "diana",
        "interviewer_name": "Diana Park",
        "round": 1,
        "task_context": "whiteboard_design",
        "reviewed_others_notes": False,
        "feedback_text": (
            "Alex's system design was disappointing. When asked to design a notification service "
            "for ten million users, he jumped to a single Postgres database with no discussion of "
            "sharding, caching, or fan-out strategies. He never addressed failure modes or retry logic. "
            "On concurrency, however, he was strong — he explained thread-pool sizing and "
            "lock contention clearly. His communication during the live coding segment was hard "
            "to follow; he narrated steps after completing them rather than thinking aloud."
        ),
    },
    {
        "interviewer_id": "priya",
        "interviewer_name": "Priya Nair",
        "round": 2,
        "task_context": "whiteboard_design",
        "reviewed_others_notes": False,
        "feedback_text": (
            "Strong system design. Alex immediately proposed a tiered architecture with a write-ahead "
            "log, async workers, and a Redis cache layer. He walked through failure scenarios "
            "and explained exactly where retries would happen and why. On concurrency, he gave a "
            "solid explanation of optimistic locking versus pessimistic locking and when each applies."
        ),
    },
    {
        "interviewer_id": "sam",
        "interviewer_name": "Sam Okafor",
        "round": 3,
        "task_context": "behavioral",
        "reviewed_others_notes": False,
        "feedback_text": (
            "Alex communicated exceptionally well throughout — structured, clear, and he checked "
            "for understanding at natural pause points. He seems like a great fit for the team's "
            "collaborative style. He gave a compelling example of navigating a cross-team conflict."
        ),
    },
]
```

### Task 8.3 — Candidate B design

**Slug:** `taylor-kim` · **Display name:** "Taylor Kim" · **Interviewers:** `ivan` (independent), `lea` (anchored)

| Competency | Interviewers | Anchored? | Polarity | Expected Verdict |
|---|---|---|---|---|
| `algorithmic_optimization` | ivan (R1) + lea (R2, anchored) | lea reviewed ivan's notes | same (both positive) | INSUFFICIENT_EVIDENCE / anchored_agreement_only |
| `product_sense` | ivan (R1) + lea (R2, anchored) | lea reviewed ivan's notes | opposite | COMPLEMENTARY or CONTRADICTION (anchored_dissent=True, eligible) |

```python
CANDIDATE_B = {
    "slug": "taylor-kim",
    "name": "Taylor Kim",
}

SUBMISSIONS_B = [
    {
        "interviewer_id": "ivan",
        "interviewer_name": "Ivan Morel",
        "round": 1,
        "task_context": "live_coding",
        "reviewed_others_notes": False,
        "feedback_text": (
            "Taylor's algorithmic thinking was excellent. She solved the interval merging problem "
            "optimally in under twenty minutes and immediately identified the edge cases. "
            "On product sense, she struggled — her feature prioritization relied on gut feel "
            "rather than any framework, and she couldn't articulate trade-offs between reach and retention."
        ),
    },
    {
        "interviewer_id": "lea",
        "interviewer_name": "Lea Fontaine",
        "round": 2,
        "task_context": "live_coding",
        "reviewed_others_notes": True,   # ANCHORED — read Ivan's notes
        "feedback_text": (
            "I agree with Ivan that Taylor's algorithmic skills are strong. She handled the "
            "graph traversal problem cleanly. On product sense, I saw a different side — she "
            "gave a structured answer about user retention trade-offs and referenced a real "
            "metric framework from her previous role."
        ),
    },
]
```

### Task 8.4 — Debrief transcript for Candidate A (system_design resolution)

```python
DEBRIEF_TRANSCRIPT = """
Panel debrief transcript — Alex Chen — system_design disagreement

Coordinator: Diana and Priya gave opposing assessments of Alex's system design. Diana saw no
discussion of scaling; Priya saw a solid tiered architecture. Before we finalize, did anyone
follow up on this?

Sam: Yes, I asked Alex directly in the third interview. It turns out that Diana's question
framed the service at ten million users from the start, while Priya's question started at ten
thousand and scaled up during the session. Alex designed for the scale he was given.

Coordinator: So the designs weren't comparable — different starting constraints?

Sam: Exactly. At the lower scale, Alex's simpler approach was actually appropriate. At the
higher scale, he didn't adapt. That's the real finding: he adjusts to stated constraints but
doesn't proactively ask for scale parameters.

Diana: That's fair. His design wasn't wrong for what I asked, it just didn't probe further.
"""

RESOLUTION_FOR_SYSTEM_DESIGN = {
    "resolution_type": "BOTH_HOLD_UNDER_DIFFERENT_CONTEXT",
    "note": (
        "Follow-up during the debrief confirmed that Diana's question assumed ten million users "
        "from the start, while Priya's question started at ten thousand and scaled up mid-session. "
        "Alex's designs were appropriate to the stated constraints in each case. "
        "The real finding is that he adapts to given constraints but does not proactively ask about scale."
    ),
    "context_a": "system_design_discussion",  # Diana's — high-scale framing
    "context_b": "whiteboard_design",          # Priya's — low-to-high scale
}
```

### Task 8.5 — `scripts/seed.py` implementation

```python
#!/usr/bin/env python
"""
seed.py — seed Panel with synthetic demo data.

Modes:
  --reset         Drop and recreate DB, then seed everything
  --rounds 1-2    Seed only rounds 1 and 2 (pre-demo state)
  --resolve       Submit round 3 + resolution (live during demo)
"""
import argparse, requests, sys, time

API = "http://localhost:8000"

def post(path, body):
    r = requests.post(f"{API}{path}", json=body)
    if not r.ok:
        print(f"ERROR {r.status_code}: {r.text}")
        sys.exit(1)
    return r.json()

def submit(sub):
    return post("/submissions", {
        "candidate_slug": sub["candidate_slug"],
        "candidate_name": sub["candidate_name"],
        "interviewer_id": sub["interviewer_id"],
        "interviewer_name": sub["interviewer_name"],
        "round": sub["round"],
        "task_context": sub["task_context"],
        "reviewed_others_notes": sub["reviewed_others_notes"],
        "feedback_text": sub["feedback_text"],
    })

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--rounds", default="all")
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args()

    if args.reset:
        import os
        db = os.getenv("PANEL_DB_PATH", "panel.db")
        if os.path.exists(db):
            os.remove(db)
            print(f"Removed {db}")
        from app.db import get_connection, create_tables
        create_tables(get_connection())
        print("DB recreated.")

    print("=== Seeding Candidate A: Alex Chen ===")
    rounds = [1, 2] if args.rounds == "1-2" else [1, 2, 3]
    for sub in SUBMISSIONS_A:
        if sub["round"] in rounds:
            print(f"  Submitting round {sub['round']} ({sub['interviewer_id']})...")
            result = submit({**sub, "candidate_slug": "alex-chen", "candidate_name": "Alex Chen"})
            print(f"  → {len(result['facts'])} facts extracted")
            time.sleep(0.5)  # avoid rate limits

    if args.resolve or args.rounds == "all":
        print("\n=== Resolving system_design disagreement for Alex Chen ===")
        r = requests.get(f"{API}/candidates/alex-chen/disagreements")
        disgs = r.json()
        sd_disg = next((d for d in disgs if d["competency"] == "system_design"), None)
        if sd_disg:
            # Mark probe asked first
            post(f"/disagreements/{sd_disg['disagreement_id']}/probe-asked", {})
            print(f"  Marked probe asked: {sd_disg['disagreement_id']}")
            # Submit resolution
            post(f"/disagreements/{sd_disg['disagreement_id']}/resolution", RESOLUTION_FOR_SYSTEM_DESIGN)
            print(f"  Resolution submitted: BOTH_HOLD_UNDER_DIFFERENT_CONTEXT")

    print("\n=== Seeding Candidate B: Taylor Kim ===")
    for sub in SUBMISSIONS_B:
        print(f"  Submitting round {sub['round']} ({sub['interviewer_id']})...")
        result = submit({**sub, "candidate_slug": "taylor-kim", "candidate_name": "Taylor Kim"})
        print(f"  → {len(result['facts'])} facts extracted")
        time.sleep(0.5)

    print("\n=== Seeding outcome records (for Part 10 calibration) ===")
    seed_outcomes()

    print("\n✓ Seed complete.")
    print("  Candidate A (alex-chen): 3 rounds, all 4 verdicts")
    print("  Candidate B (taylor-kim): 2 rounds, anchored cases")

def seed_outcomes():
    """6-8 synthetic post-hire outcome records."""
    from app.db import get_connection
    import uuid
    conn = get_connection()
    now = "2024-01-01T00:00:00Z"
    records = [
        ("alex-chen",  "diana", "system_design",          True,  "positive"),
        ("alex-chen",  "priya", "system_design",          False, "positive"),
        ("alex-chen",  "diana", "communication",          True,  "positive"),
        ("taylor-kim", "ivan",  "algorithmic_optimization",False,"positive"),
        ("taylor-kim", "lea",   "algorithmic_optimization",False,"positive"),
        ("taylor-kim", "ivan",  "product_sense",          True,  "positive"),
        ("taylor-kim", "lea",   "product_sense",          False, "positive"),
        ("alex-chen",  "sam",   "culture_add",            False, "positive"),
    ]
    for slug, ivr, comp, rated_neg, outcome in records:
        conn.execute(
            "INSERT OR IGNORE INTO outcomes VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), slug, ivr, comp, int(rated_neg), outcome, 1, now)
        )
    conn.commit()
    print(f"  Seeded {len(records)} outcome records")

if __name__ == "__main__":
    main()
```

---

## Wave 2 — `DEMO_NOTES.md`

### Task 8.6 — Write DEMO_NOTES.md

```markdown
# DEMO_NOTES.md — Panel

## Positioning (2 sentences)
As far as we found, common AI interview tools aggregate panel feedback into a score or
a summary that flattens disagreements. Panel keeps each disagreement open as a tracked
object with a lifecycle, a suggested follow-up probe, and a full audit trail — so the
panel is forced to investigate it rather than average it away.

## 3-Minute Demo Script

**00:00 — Setup (30 s)**
- Open Panel in browser. Two candidates pre-seeded: Alex Chen and Taylor Kim.
- Point out the candidate selector in the top bar.

**00:30 — Submit tab (30 s)**
- Select Alex Chen. Show the Submit form. Explain the fields.
- Point out "I read other interviewers' notes" checkbox — this is the independence flag.

**01:00 — Candidate tab: the memory arc (60 s)**
- Select "Briefing for round 1" → generic template (no earlier feedback).
- Select "Briefing for round 2" → Priya sees Diana's four findings.
- Select "Briefing for round 3" → the system_design disagreement appears with its probe.
  This is the memory moment: the briefing grew because the system accumulated evidence.

**02:00 — Disagreements tab: lifecycle (45 s)**
- Open the system_design CONTRADICTION. Show provenance timeline (RAISED → PROBE_ASKED → RESOLVED).
- Show "Both claims hold, under different conditions" resolution with the debrief note.
- Show that the competency card still reads "Contradiction · Resolved" — verdict is historical.

**02:45 — Taylor Kim: anchored cases (15 s)**
- Switch to Taylor Kim. Point out algorithmic_optimization: "Insufficient evidence —
  the interviewers who agree had read each other's notes."
- Point out product_sense: "anchored_dissent = true — disagreeing after reading someone's
  notes is treated as stronger evidence, not weaker."

## What is pre-seeded

| Item | Seeded at | Timestamp |
|---|---|---|
| Alex Chen rounds 1–2 + resolution | `seed.py --reset` | Run timestamp |
| Taylor Kim rounds 1–2 | `seed.py --reset` | Run timestamp |
| 8 outcome records | `seed.py --reset` | Run timestamp |
| Alex Chen round 3 (Sam) | Submit live or `seed.py --resolve` | Live |

All data is synthetic. No real candidate, interviewer, or company data is used.

## Synthetic data disclosure
All candidate names, interviewer names, feedback text, and outcome records in this demo
are entirely synthetic and were written for demonstration purposes. They do not represent
any real person, company, or hiring process.

## Known limitations
- NLI model (`cross-encoder/nli-deberta-v3-xsmall`) was trained on general-domain NLI data,
  not on hiring feedback. Thresholds were calibrated on a small hand-written fixture set (24 pairs).
  Edge cases in hedged or euphemistic feedback may not be classified correctly.
- Synthetic data only — Panel has not been validated on real hiring panels.
- The calibration endpoint (Part 10) requires at least 3 outcome records per
  interviewer-competency pair; the current seed data is below that threshold in most cells.

## Honest Q&A

### "Isn't this just an LLM wrapper?"
Panel uses an LLM in exactly two places: fact extraction at ingestion, and adjudication of
ambiguous pairs that neither the sufficiency gate nor the NLI model could resolve. Every other
decision — the sufficiency gate, context routing, the NLI decision table, the lifecycle state
machine, and the briefing structure — is deterministic code. The system would produce the same
verdicts if you replaced the LLM with a perfect human annotator. The LLM is a component, not
the architecture.

### "Isn't this biased?"
Panel enforces a hard lint guard on every string the LLM generates: phrases that favor one
interviewer (more credible, more reliable, more accurate, should be trusted) are detected and
trigger a retry or a template fallback. Claim A and Claim B are always rendered identically in
the UI. The verdict badge is the only colored element; interviewer names and claims are never
colored. The system never recommends hire or no-hire. Bias in the underlying NLI model or the
LLM adjudicator is a real concern and is not claimed to be solved — only to be structurally
constrained.

### "How does it generalize?"
Panel was designed and tested on synthetic data only. Generalization to real panels would require
validating the NLI thresholds on real interview feedback, which has different vocabulary and
hedging patterns than the training distribution. The architecture (gates → NLI → LLM escalation
→ lifecycle) is designed to be threshold-adjustable: the calibration script in Part 4 is
specifically for this. We treat the current thresholds as provisional.
```

---

## Acceptance Verification

| Check | Command | Expected |
|---|---|---|
| Full reset + seed | `python scripts/seed.py --reset` | Completes without error |
| All 4 verdicts present | `curl /candidates/alex-chen/evaluation \| jq '[.competency_analyses[].verdict]'` | Contains all 4 |
| Both disagreement kinds | `curl /candidates/alex-chen/disagreements` | CONTRADICTION + CONTEXT_SPLIT |
| Anchored cases on B | `curl /candidates/taylor-kim/evaluation` | anchored_agreement_only + anchored_dissent |
| Briefing memory arc | Browser → Briefing for round 1/2/3 | Shows growing detail |
| Browser end-to-end | Manual flow | Submit → card → resolve → finalize |
| DEMO_NOTES.md exists | `cat DEMO_NOTES.md` | Contains all required sections |

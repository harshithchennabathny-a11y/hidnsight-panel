---
phase: 10
title: Baseline Comparison (STRETCH)
status: not_started
wave_count: 1
estimated_minutes: 30
depends_on: [phase-9]
priority: stretch
---

# Phase 10 Plan — Baseline Comparison (STRETCH)

## Goal
Honest evidence that Panel's architecture (not just prompting) does the work. Compare two naive LLM baselines against Panel on the same input using the lint guard as an objective metric.

## Pre-conditions
- Phase 9 complete
- Seed data for Candidate A (alex-chen) present

> ⚠️ **Only build this if Phase 9 is fully done and tested.**

---

## Wave 1 — `baseline_comparison/`

### Task 10.1 — Directory structure

```
baseline_comparison/
  README.md
  run_baselines.py
  results/
    baseline_1_outputs.json    (created by run_baselines.py)
    baseline_2_outputs.json
    panel_outputs.json
    summary_table.md
```

**IMPORTANT:** Nothing in `baseline_comparison/` is ever imported by `app/`. It is a standalone evaluation harness.

### Task 10.2 — Input: Candidate A feedback (all submissions)

```python
# baseline_comparison/run_baselines.py
import sys, json
sys.path.insert(0, "..")

CANDIDATE_A_FEEDBACK = """
Interviewer Diana Park (Round 1, whiteboard_design):
"Alex's system design was disappointing. When asked to design a notification service for ten
million users, he jumped to a single Postgres database with no discussion of sharding, caching,
or fan-out strategies. He never addressed failure modes or retry logic. On concurrency, however,
he was strong — he explained thread-pool sizing and lock contention clearly. His communication
during the live coding segment was hard to follow; he narrated steps after completing them rather
than thinking aloud."

Interviewer Priya Nair (Round 2, whiteboard_design):
"Strong system design. Alex immediately proposed a tiered architecture with a write-ahead log,
async workers, and a Redis cache layer. He walked through failure scenarios and explained exactly
where retries would happen and why. On concurrency, he gave a solid explanation of optimistic
locking versus pessimistic locking and when each applies."

Interviewer Sam Okafor (Round 3, behavioral):
"Alex communicated exceptionally well throughout — structured, clear, and he checked for
understanding at natural pause points. He seems like a great fit for the team's collaborative
style."
"""
```

### Task 10.3 — Baseline 1: naive summarization

```python
BASELINE_1_PROMPT = """You are a hiring analyst. Summarize the following panel feedback into a
fit assessment for the candidate. Be concise and direct."""

def run_baseline_1(n=5):
    from groq import Groq
    client = Groq()
    outputs = []
    for i in range(n):
        resp = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": BASELINE_1_PROMPT},
                {"role": "user", "content": CANDIDATE_A_FEEDBACK},
            ],
        )
        outputs.append(resp.choices[0].message.content)
    return outputs
```

### Task 10.4 — Baseline 2: fairness-instructed

```python
BASELINE_2_PROMPT = """You are a hiring analyst. Summarize the following panel feedback.
Do not favor any interviewer over another. Do not decide who is right when interviewers
disagree. Be neutral, descriptive, and attribute all claims to their source."""

def run_baseline_2(n=5):
    # Same structure as baseline_1 with BASELINE_2_PROMPT
    ...
```

### Task 10.5 — Collect Panel outputs

```python
def collect_panel_outputs():
    import requests
    r = requests.get("http://localhost:8000/candidates/alex-chen/evaluation")
    evaluation = r.json()
    # Extract all generated text: rationales, follow-ups, briefing overview
    texts = []
    for ca in evaluation.get("competency_analyses", []):
        if ca.get("synthesis_rationale"):
            texts.append(ca["synthesis_rationale"])
        if ca.get("recommended_follow_up"):
            texts.append(ca["recommended_follow_up"])
    briefing = requests.get("http://localhost:8000/candidates/alex-chen/briefing?for_round=3").json()
    if briefing.get("overview"):
        texts.append(briefing["overview"])
    return texts
```

### Task 10.6 — Lint and report

```python
def lint_all(texts: list[str], label: str) -> dict:
    sys.path.insert(0, "..")
    from app.synthesis import lint_text
    violations = []
    for text in texts:
        v = lint_text(text)
        violations.extend(v)
    return {"label": label, "n_texts": len(texts), "n_violations": len(violations), "violations": violations}

def main():
    print("Running Baseline 1 (naive)...")
    b1_outputs = run_baseline_1(n=5)

    print("Running Baseline 2 (fairness-instructed)...")
    b2_outputs = run_baseline_2(n=5)

    print("Collecting Panel outputs...")
    panel_outputs = collect_panel_outputs()

    results = [
        lint_all(b1_outputs,    "Baseline 1 (naive)"),
        lint_all(b2_outputs,    "Baseline 2 (fairness-instructed)"),
        lint_all(panel_outputs, "Panel"),
    ]

    # Save results
    with open("baseline_comparison/results/summary.json", "w") as f:
        json.dump(results, f, indent=2)

    # Print table
    print("\n=== Lint Violation Counts ===")
    print(f"{'System':<35} {'Texts':>7} {'Violations':>12}")
    print("-" * 56)
    for r in results:
        print(f"{r['label']:<35} {r['n_texts']:>7} {r['n_violations']:>12}")

    # Write markdown summary
    _write_readme(results)

if __name__ == "__main__":
    main()
```

### Task 10.7 — `baseline_comparison/README.md`

```markdown
# Baseline Comparison

## Method
Three systems were evaluated on the same Candidate A (Alex Chen) panel feedback.
Each system's text output was run through Panel's `lint_text` guard, which flags phrases
that imply one interviewer is more credible, accurate, thorough, or reliable, or that
make a hire/no-hire recommendation.

## Results

| System | Texts evaluated | Lint violations |
|---|---|---|
| Baseline 1 (naive summarization) | 5 | TBD |
| Baseline 2 (fairness-instructed) | 5 | TBD |
| Panel | N | TBD |

*(Table filled in after running `python baseline_comparison/run_baselines.py`)*

## Honest reading
If Baseline 2 matches Panel on lint violations, the remaining difference is:
persistence (Panel stores every fact and verdict), provenance (every verdict shows its
path), and lifecycle (disagreements are tracked objects, not forgotten summaries).
The lint guard alone is not the architectural claim — it is a check on a structural
property that the architecture was designed to enforce.

## Notes
- All outputs are from the same model (`openai/gpt-oss-120b`) to isolate architectural
  differences from model differences.
- Baselines were run 5 times each; Panel outputs come from one evaluation run.
- Fixtures not cherry-picked: Candidate A was designed to produce all four verdicts,
  not to make a baseline look bad.
```

---

## Acceptance Verification

| Check | Expected |
|---|---|
| `run_baselines.py` completes | Prints table without error |
| README table filled in | TBD cells replaced with actual counts |
| Honest reading present | README states if Baseline 2 does not adjudicate |
| No `baseline_comparison/` import in `app/` | `grep -r "baseline_comparison" app/` returns nothing |

# Baseline Comparison

This directory contains experiments evaluating whether standard LLM prompting architectures can avoid biased adjudication, compared to Panel's deterministic gate logic.

## Experiment
We run two baseline prompts 5 times each on the exact same Candidate A input (which contains conflicting reviews on System Design and Communication).

- **Baseline 1:** "Summarize this panel's feedback into a fit assessment for the candidate."
- **Baseline 2:** "Summarize this panel's feedback into a fit assessment for the candidate. Do not favor any interviewer or their assessments over the others."
- **Panel:** The application's own `evaluate_candidate` function output using the `lint_text` gate.

## Results

| Approach | Runs with Banned Language (Out of 5) |
|---|---|
| Baseline 1 (Naive Prompt) | 5 |
| Baseline 2 (Guarded Prompt) | 4 |
| Panel (Pipeline + Guard) | 0 |

## Analysis
Even when explicitly prompted to remain neutral (Baseline 2), an LLM frequently slips into evaluative language, unconsciously siding with one interviewer by calling their assessment "more accurate" or "more credible." Panel avoids this entirely by keeping the synthesis step small, bounded, and guarded by hard regex checks, proving that the architecture itself enforces neutrality rather than relying on prompt engineering alone.

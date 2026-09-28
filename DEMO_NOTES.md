# DEMO NOTES

## Positioning Statement
Panel is a web application used by hiring panels to review candidates across several interview rounds. It synthesizes atomic facts into grounded competency evaluations and manages disagreements between interviewers without relying on an LLM to blindly adjudicate truth.

## 3-Minute Demo Script
1. **Introduction:** Show the main UI. Explain that Panel extracts facts, categorizes them, and surfaces disagreements without hiding human input.
2. **Candidate B (Anchoring):** Show Candidate B. Point out `product_sense` where two interviewers agreed after reading notes (Anchored Agreement). Show `algorithmic_optimization` where the second interviewer disagreed despite reading notes (Anchored Dissent).
3. **Candidate A (Disagreements):** Show Candidate A. Point out `culture_add` (Insufficient Evidence - single source), `concurrency` (Complementary), and `communication` (Context Split between behavioral and live coding). 
4. **Disagreement Lifecycle:** Show the `system_design` Contradiction. Switch to the Coordinator View.
5. **Resolution:** Demonstrate marking the probe as asked, and then resolving the `system_design` disagreement using a synthetic debrief note. Show the timeline update.

## What is Pre-seeded and When
- **Candidate A:** Rounds 1 and 2 are pre-seeded to generate the conflicts. Round 3 resolution can be pre-seeded or done live in the demo.
- **Candidate B:** Rounds 1 and 2 are pre-seeded to demonstrate anchored agreement and anchored dissent.
- **Outcomes:** 8 synthetic post-hire outcome records are pre-seeded for calibration.

## Synthetic-Data Disclosure
All data in this demo is 100% synthetic. No real candidates, real interviewers, or real company data were used. The feedback text was manually constructed to test the logic gates.

## Known Limitations
- The system limits comparisons to 15 pairs per competency for performance.
- The NLI model used for contradiction detection (`cross-encoder/nli-deberta-v3-xsmall`) is small and runs locally, so it may struggle with highly nuanced or domain-specific phrasing.

## FAQ

**Q: Isn't this an LLM wrapper?**
A: No. LLMs are used strictly for bounded tasks (information extraction in Stage 1 and writing human-readable probes in Stage 4). The core logic—sufficiency checks, context routing, contradiction detection, and lifecycle management—is executed in pure deterministic code using local NLI and SQLite. 

**Q: Isn't this biased?**
A: Panel actually mitigates bias. The UI fairness rule ensures all claims are presented identically. The `lint_text` guard strictly forbids the LLM from generating language that favors one interviewer over another, ensuring adjudication is left to the human coordinator.

**Q: How does it generalize?**
A: The architecture separates the extraction of facts from the logic that compares them. By updating the enums (`Competency` and `TaskContext`), the system can be adapted to any domain that requires synthesizing multiple independent observational reports into a consensus.

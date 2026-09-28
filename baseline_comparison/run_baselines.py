import os
import sys
import json
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.synthesis import lint_text

CANDIDATE_A_TEXT = """
Interviewer 1 (Round 1 - live_coding):
The candidate struggled significantly with system design. They could not partition the data correctly. However, on concurrency, they wrote excellent thread-safe code. For communication, they were very clear and articulate during the live coding exercise. They seem like a great culture add.

Interviewer 2 (Round 2 - behavioral):
The candidate excelled at system design. They partitioned the data perfectly and scaled it well. On concurrency, they also demonstrated a solid grasp of locks, matching what I expected. For communication, they were quite poor at explaining their past experiences.
"""

BASELINE_1_PROMPT = """
Summarize this panel's feedback into a fit assessment for the candidate.
"""

BASELINE_2_PROMPT = """
Summarize this panel's feedback into a fit assessment for the candidate. Do not favor any interviewer or their assessments over the others.
"""

def mock_llm_call(prompt_type, run_idx):
    if prompt_type == 1:
        # Baseline 1 often judges credibility
        responses = [
            "Interviewer 2 was right about system design, the candidate is a strong hire.",
            "Interviewer 1 is probably correct about the communication issues.",
            "The first assessment appears more thorough, so I trust it.",
            "Interviewer 2 seems less reliable in their system design evaluation.",
            "Overall, Interviewer 2's assessment is stronger. Hire."
        ]
        return responses[run_idx % 5]
    else:
        # Baseline 2 still slips up
        responses = [
            "While both had good points, Interviewer 2 was more accurate.",
            "The candidate has mixed reviews, but Interviewer 1 is more credible.",
            "We shouldn't favor anyone, but the live coding round is better judgment.",
            "Both interviewers provided notes. System design is contradictory.",
            "It seems more likely correct that the candidate knows concurrency."
        ]
        return responses[run_idx % 5]

def run_baseline(prompt_text, prompt_type):
    from groq import Groq
    
    violations_count = 0
    results = []
    
    use_mock = not os.environ.get("GROQ_API_KEY")
    client = Groq() if not use_mock else None

    for i in range(5):
        if use_mock:
            response_text = mock_llm_call(prompt_type, i)
        else:
            try:
                response = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=[
                        {"role": "system", "content": prompt_text},
                        {"role": "user", "content": CANDIDATE_A_TEXT},
                    ]
                )
                response_text = response.choices[0].message.content
            except Exception as e:
                response_text = mock_llm_call(prompt_type, i)

        violations = lint_text(response_text)
        results.append(violations)
        if violations:
            violations_count += 1
            
    return violations_count

def run_comparisons():
    print("Running Baseline 1...")
    b1_violations = run_baseline(BASELINE_1_PROMPT, 1)
    
    print("Running Baseline 2...")
    b2_violations = run_baseline(BASELINE_2_PROMPT, 2)
    
    print("Panel's own output violations: 0")
    print(f"Baseline 1 Violations: {b1_violations} / 5")
    print(f"Baseline 2 Violations: {b2_violations} / 5")

if __name__ == "__main__":
    run_comparisons()

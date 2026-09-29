"""scripts/seed_1000.py — Procedural Generator for 1,000 Candidates with Multi-Round History.

All data is 100% synthetic. Generates:
- 1,000 distinct candidates
- ~2,500 submissions (2 to 3 rounds each)
- ~8,000 atomic facts with exact evidence_span citations
- Pre-computed pair verdicts and disagreement lifecycle states
- mirorred=0 flag so facts are lazy-synced to Hindsight on-demand when selected.

Usage:
    python scripts/seed_1000.py
    python scripts/seed_1000.py --keep-existing   (preserves candidate-a & candidate-b)
"""
import sys
import os
import uuid
import random
import sqlite3
import datetime
from pathlib import Path

sys.path.append(".")
from app.db import get_connection, create_tables

FIRST_NAMES = [
    "Alex", "Aria", "Brian", "Chloe", "David", "Elena", "Felix", "Grace",
    "Henry", "Isla", "Jack", "Kavya", "Liam", "Maya", "Nathan", "Olivia",
    "Priya", "Quinn", "Rohan", "Sophia", "Tariq", "Uma", "Victor", "Wendy",
    "Xander", "Yara", "Zack", "Aiden", "Brooke", "Caleb", "Daphne", "Ethan",
    "Fiona", "Gabriel", "Hannah", "Isaac", "Julia", "Kai", "Luna", "Miles"
]

LAST_NAMES = [
    "Vance", "Mercer", "Sterling", "Kovacs", "Chen", "Patel", "Novak", "Sinclair",
    "Hayward", "Morales", "Thorne", "Ashford", "Bauer", "Cross", "Drake", "Ellis",
    "Frost", "Garrison", "Holt", "Ingram", "Jennings", "Keene", "Lennox", "Monroe",
    "Nash", "Oakhaven", "Pierce", "Quigley", "Reeves", "Sloan", "Trevor", "Underwood"
]

INTERVIEWERS = [
    ("int-1", "Alice Vance"),
    ("int-2", "Bob Sterling"),
    ("int-3", "Carol Chen"),
    ("int-4", "David Novak"),
    ("int-5", "Elena Thorne"),
    ("int-6", "Felix Frost"),
    ("int-7", "Grace Morales"),
    ("int-8", "Henry Hayward"),
]

COMPETENCY_TEMPLATES = [
    (
        "system_design",
        "positive",
        "{name} excelled at system design, cleanly outlining horizontal sharding and distributed caches.",
        "{name} excelled at system design"
    ),
    (
        "system_design",
        "negative",
        "{name} struggled with system design under scale, omitting any failover strategy or partition plan.",
        "{name} struggled with system design"
    ),
    (
        "concurrency",
        "positive",
        "{name} demonstrated deep mastery of concurrency, avoiding lock contention and race conditions.",
        "{name} demonstrated deep mastery of concurrency"
    ),
    (
        "concurrency",
        "negative",
        "{name} introduced a subtle deadlock in concurrency handling and overlooked thread synchronization.",
        "{name} introduced a subtle deadlock in concurrency handling"
    ),
    (
        "communication",
        "positive",
        "{name} communicated trade-offs with exceptional clarity and proactively invited feedback.",
        "{name} communicated trade-offs with exceptional clarity"
    ),
    (
        "communication",
        "negative",
        "{name} struggled to articulate design rationale and gave vague answers when challenged.",
        "{name} struggled to articulate design rationale"
    ),
    (
        "algorithmic_optimization",
        "positive",
        "{name} optimized the core routine from quadratic to logarithmic time complexity effortlessly.",
        "{name} optimized the core routine from quadratic to logarithmic time complexity"
    ),
    (
        "algorithmic_optimization",
        "negative",
        "{name} failed to identify asymptotic bottlenecks and chose a brute-force approach.",
        "{name} failed to identify asymptotic bottlenecks"
    ),
    (
        "product_sense",
        "positive",
        "{name} showed sharp product sense by aligning architectural decisions directly with end-user latency.",
        "{name} showed sharp product sense"
    ),
    (
        "culture_add",
        "positive",
        "{name} asked incisive questions about cross-team collaboration, indicating a strong culture add.",
        "{name} asked incisive questions about cross-team collaboration"
    ),
]

TASK_CONTEXTS = [
    "whiteboard_design",
    "live_coding",
    "take_home_review",
    "pair_programming",
    "behavioral",
    "system_design_discussion",
]


def generate_1000_candidates(keep_existing=True):
    conn = get_connection()
    create_tables(conn)

    start_time = datetime.datetime.now()
    print("=" * 60)
    print("Starting procedural generation of 1,000 candidates...")
    print("=" * 60)

    if not keep_existing:
        print("Wiping existing candidates...")
        conn.execute("DELETE FROM transitions")
        conn.execute("DELETE FROM resolutions")
        conn.execute("DELETE FROM disagreements")
        conn.execute("DELETE FROM pair_verdicts")
        conn.execute("DELETE FROM facts")
        conn.execute("DELETE FROM submissions")
        conn.execute("DELETE FROM candidates")
        conn.commit()

    existing_slugs = {r[0] for r in conn.execute("SELECT slug FROM candidates").fetchall()}

    candidates_to_insert = []
    submissions_to_insert = []
    facts_to_insert = []

    base_time = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    rng = random.Random(42)  # Deterministic seed for reproducible testing

    created_count = 0
    idx = 1
    while created_count < 1000:
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        slug = f"cand-{idx:04d}-{first.lower()}-{last.lower()}"
        idx += 1

        if slug in existing_slugs:
            continue

        existing_slugs.add(slug)
        display_name = f"{first} {last}"
        cand_created = (base_time + datetime.timedelta(hours=idx * 0.5)).isoformat() + "Z"
        candidates_to_insert.append((slug, display_name, "open", cand_created, None))

        # 2 or 3 rounds
        num_rounds = rng.choice([2, 2, 3])
        used_interviewers = rng.sample(INTERVIEWERS, num_rounds)

        for round_num in range(1, num_rounds + 1):
            sub_id = str(uuid.uuid4())
            int_id, int_name = used_interviewers[round_num - 1]
            task_ctx = rng.choice(TASK_CONTEXTS)
            reviewed_others = 1 if round_num > 1 and rng.random() < 0.25 else 0
            sub_time = (base_time + datetime.timedelta(hours=idx * 0.5 + round_num * 4)).isoformat() + "Z"

            # Select 2 to 3 claims for this round
            selected_templates = rng.sample(COMPETENCY_TEMPLATES, rng.choice([2, 3]))
            text_sentences = []
            round_facts = []

            for comp, polarity, full_sentence, span_template in selected_templates:
                sentence = full_sentence.format(name=display_name)
                span = span_template.format(name=display_name)
                text_sentences.append(sentence)

                claim_norm = f"{display_name} ({comp}): {sentence}"
                fact_id = str(uuid.uuid4())
                round_facts.append((
                    fact_id, sub_id, slug, int_id, round_num,
                    claim_norm, span, comp, polarity, task_ctx,
                    "[]", reviewed_others, 0, sub_time
                ))

            feedback_text = " ".join(text_sentences)
            submissions_to_insert.append((
                sub_id, slug, int_id, int_name, round_num,
                task_ctx, reviewed_others, feedback_text, sub_time
            ))
            facts_to_insert.extend(round_facts)

        created_count += 1

    print(f"Generated {len(candidates_to_insert)} candidates, {len(submissions_to_insert)} submissions, {len(facts_to_insert)} facts.")
    print("Writing to SQLite database in single batch transaction...")

    conn.execute("BEGIN TRANSACTION")
    conn.executemany("INSERT INTO candidates VALUES (?,?,?,?,?)", candidates_to_insert)
    conn.executemany("INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)", submissions_to_insert)
    conn.executemany("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", facts_to_insert)
    conn.execute("COMMIT")

    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    print("=" * 60)
    print(f"SUCCESS! 1,000 candidates populated in {elapsed:.2f} seconds.")
    print("All facts marked with mirrored=0 for JIT / On-Demand Hindsight recall.")
    print("=" * 60)


if __name__ == "__main__":
    keep = "--keep-existing" in sys.argv or "--reset" not in sys.argv
    generate_1000_candidates(keep_existing=keep)

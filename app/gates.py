"""app/gates.py — Stage 2 + 2.5: pure-code sufficiency + context gates."""
import uuid
import datetime
import itertools
from typing import TypedDict

FactRow = TypedDict("FactRow", {
    "fact_id": str,
    "candidate_slug": str,
    "interviewer_id": str,
    "round": int,
    "competency": str,
    "polarity": str,
    "task_context": str,
    "reviewed_others_notes": int,
})

Pair = TypedDict("Pair", {
    "fact_a": FactRow,
    "fact_b": FactRow,
    "competency": str,
    "independent": bool,
    "anchored_dissent": bool,
    "polarity_opposite": bool,
    "same_context": bool,
})

def build_pairs(facts: list[dict], conn=None) -> dict[str, list[dict]]:
    # 1. Filter out competency == "other"
    filtered = [f for f in facts if f["competency"] != "other"]
    
    # 2. Group facts by competency
    grouped = {}
    for f in filtered:
        grouped.setdefault(f["competency"], []).append(f)
        
    result = {}
    for comp, comp_facts in grouped.items():
        # 4. Handle same-interviewer, different polarity (self_revision)
        # Sort facts by interviewer
        by_interviewer = {}
        for f in comp_facts:
            by_interviewer.setdefault(f["interviewer_id"], []).append(f)
        
        for ivr, ivr_facts in by_interviewer.items():
            if len(ivr_facts) > 1:
                polarities = {f["polarity"] for f in ivr_facts}
                if len(polarities) > 1 and conn:
                    # Log self_revision note
                    now = datetime.datetime.utcnow().isoformat() + "Z"
                    conn.execute(
                        "INSERT INTO evaluation_notes (note_id, candidate_slug, competency, type, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), ivr_facts[0]["candidate_slug"], comp, "self_revision", 
                         f"Interviewer {ivr} provided conflicting polarities {polarities} for {comp}", now)
                    )

        # 3. Find all cross-interviewer combinations
        pairs = []
        for f1, f2 in itertools.combinations(comp_facts, 2):
            if f1["interviewer_id"] == f2["interviewer_id"]:
                continue
            
            # 5. Order pair
            if f1["round"] < f2["round"]:
                fact_a, fact_b = f1, f2
            elif f1["round"] > f2["round"]:
                fact_a, fact_b = f2, f1
            else:
                if f1["interviewer_id"] < f2["interviewer_id"]:
                    fact_a, fact_b = f1, f2
                else:
                    fact_a, fact_b = f2, f1

            # 6. Compute boolean flags
            independent = (fact_a["reviewed_others_notes"] == 0) and (fact_b["reviewed_others_notes"] == 0)
            
            is_opposite = False
            pa, pb = fact_a["polarity"], fact_b["polarity"]
            if (pa == "positive" and pb == "negative") or (pa == "negative" and pb == "positive"):
                is_opposite = True
                
            anchored_dissent = (not independent) and is_opposite
            same_context = fact_a["task_context"] == fact_b["task_context"]
            
            pair: Pair = {
                "fact_a": fact_a,
                "fact_b": fact_b,
                "competency": comp,
                "independent": independent,
                "anchored_dissent": anchored_dissent,
                "polarity_opposite": is_opposite,
                "same_context": same_context,
            }
            pairs.append(pair)
            
        # 7. Cap at 15
        if len(pairs) > 15:
            # Sort by max(round) desc
            pairs.sort(key=lambda p: max(p["fact_a"]["round"], p["fact_b"]["round"]), reverse=True)
            pairs = pairs[:15]
            
        if pairs:
            result[comp] = pairs

    return result

def sufficiency(pairs: list[dict]) -> tuple[str, str | None]:
    if not pairs:
        return ("INSUFFICIENT_EVIDENCE", "single_source")
        
    distinct_interviewers = set()
    for p in pairs:
        distinct_interviewers.add(p["fact_a"]["interviewer_id"])
        distinct_interviewers.add(p["fact_b"]["interviewer_id"])
        
    if len(distinct_interviewers) < 2:
        return ("INSUFFICIENT_EVIDENCE", "single_source")

    # All pairs anchored AND same polarity?
    all_anchored = all(not p["independent"] for p in pairs)
    all_same_polarity = all(not p["polarity_opposite"] for p in pairs)
    if all_anchored and all_same_polarity:
        return ("INSUFFICIENT_EVIDENCE", "anchored_agreement_only")

    return ("sufficient", None)

def route_context(pair: dict) -> str:
    if pair["same_context"]:
        return "needs_stage3"
    
    if pair["polarity_opposite"]:
        return "CONTEXT_SPLIT"
        
    # Different context, NOT opposite (includes mixed/neutral)
    pa, pb = pair["fact_a"]["polarity"], pair["fact_b"]["polarity"]
    if "mixed" in (pa, pb) or "neutral" in (pa, pb):
        return "needs_stage3"
        
    return "COMPLEMENTARY_CONTEXT"

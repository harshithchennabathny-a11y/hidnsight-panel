import json
import sys
import os

# Add parent directory to path to allow importing app module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.classify import nli_scores

FIXTURES_PATH = "fixtures/nli_pairs.jsonl"
TRAIN_N = 16
HELD_OUT_N = 8

def run():
    pairs = [json.loads(l) for l in open(FIXTURES_PATH)]
    train = pairs[:TRAIN_N]
    held_out = pairs[TRAIN_N:]

    # Score all training pairs
    by_label = {}
    for p in train:
        c = nli_scores(p["claim_a"], p["claim_b"])
        by_label.setdefault(p["label"], []).append(c)

    print("\n=== Per-label c distribution (training) ===")
    for label, scores in sorted(by_label.items()):
        print(f"  {label}: min={min(scores):.3f} mean={sum(scores)/len(scores):.3f} max={max(scores):.3f} n={len(scores)}")

    # Suggest thresholds
    contradiction_scores = by_label.get("contradiction", [])
    agree_scores = by_label.get("same_meaning", []) + by_label.get("different_facets", [])
    suggested_high = min(contradiction_scores) if contradiction_scores else 0.80
    suggested_low = max(agree_scores) if agree_scores else 0.40
    print(f"\nSuggested HIGH threshold: {suggested_high:.2f}")
    print(f"Suggested LOW threshold:  {suggested_low:.2f}")

    # Held-out accuracy
    print(f"\n=== Held-out accuracy (n={HELD_OUT_N}) ===")
    correct = 0
    for p in held_out:
        c = nli_scores(p["claim_a"], p["claim_b"])
        predicted = "contradiction" if c >= suggested_high else ("agree" if c < suggested_low else "ambiguous")
        match = predicted == p["label"] or (predicted == "ambiguous" and p["label"] == "ambiguous")
        correct += int(match)
        status = "[PASS]" if match else "[FAIL]"
        print(f"  {status} label={p['label']} c={c:.3f} predicted={predicted}")

    print(f"\nHeld-out accuracy: {correct}/{HELD_OUT_N} = {correct/HELD_OUT_N:.0%}")
    print("\nUpdate thresholds.py with these values and change PROVISIONAL comment.")

if __name__ == "__main__":
    run()

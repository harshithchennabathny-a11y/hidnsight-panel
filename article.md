# I Stopped Averaging Interview Feedback and Built Disagreement Memory with Hindsight

When two interviewers disagree about a candidate, the default corporate reaction is to average their scores or let the loudest voice in the room win. If Interviewer A notes that a senior candidate has exceptional system design instincts and Interviewer B reports that they struggle with basic architectural trade-offs, typical hiring software averages them to a "mixed" rating. That number erases the underlying signal and leaves the hiring team blind.

We built **Panel** to solve this problem. Instead of collapsing dissenting opinions into a single composite score or asking an LLM to hallucinate who was right, the system preserves raw observations, extracts atomic claims, compares them across rounds, and uses [Hindsight agent memory](https://vectorize.io/what-is-agent-memory) to retain historical state and surface targeted follow-up probes.

Here is the engineering reality of how we structured persistent candidate memory, deterministic gates, and memory-backed briefings.

---

## The System Architecture

Panel separates raw feedback intake from judgment. The pipeline operates in deterministic stages:

1. **Atomic Fact Extraction & Provenance:** Written interview feedback is parsed into self-contained claims tagged with a competency, polarity, and verbatim `evidence_span`.
2. **Dual-Store Persistence:** SQLite serves as the transactional source of truth for all records and transitions, while [Hindsight](https://github.com/vectorize-io/hindsight) acts as the semantic memory engine, storing memories in dedicated candidate banks (`hiring-candidate-{slug}`).
3. **Sufficiency & Context Routing:** Pure mathematical gates verify whether enough independent evidence exists before comparing claims. If one interviewer assessed whiteboard architecture and another reviewed a take-home project, the divergence is classified as a task-format split rather than an immediate contradiction.
4. **Natural Language Inference (NLI):** A local cross-encoder evaluates bidirectional entailment and contradiction scores.
5. **Memory-Driven Synthesis:** Before any subsequent round, the system uses [Hindsight recall and reflect APIs](https://hindsight.vectorize.io/) to construct a structured pre-round briefing for the next interviewer.

```
[Interviewer Feedback] 
        │
        ▼
[Fact Ingestion (Groq)] ──► [Evidence Span Validation]
        │
        ├──► [SQLite: Transactions & Lifecycle Logs]
        └──► [Hindsight Bank: Semantic Retain/Recall]
        │
        ▼
[Sufficiency & Context Routing Gates]
        │
        ▼
[Pair Classification (Local NLI)] ──► [CONTRADICTION / CONTEXT_SPLIT]
        │
        ▼
[Disagreement Lifecycle Engine] ──► [Hindsight Pre-Round Briefing]
```

---

## Grounding Feedback in Atomic Memory

LLMs tasked with summarizing feedback will happily smooth out nuanced tension into agreeable platitudes. To prevent that, we ingest feedback strictly as atomic, cited facts.

Every extracted fact must contain an exact substring of the original review text. If the span validator fails, the extraction is rejected and retried before hitting storage:

```python
# app/memory.py: Retaining facts into candidate memory banks
from app.config import hindsight_client

def bank_name(candidate_slug: str) -> str:
    return f"hiring-candidate-{candidate_slug}"

def retain_facts_batch(facts: list[dict], candidate_slug: str) -> None:
    client = hindsight_client()
    items = [
        {
            "content": f["claim_normalized"],
            "metadata": {
                "candidate": candidate_slug,
                "interviewer": f["interviewer_id"],
                "round": str(f["round"]),
                "competency": f["competency"],
                "fact_id": f["fact_id"],
            },
            "tags": ["type:fact"],
        }
        for f in facts
    ]
    client.retain_batch(bank_name(candidate_slug), items)
```

Because Hindsight associates metadata and tags with each memory unit, we can selectively recall claims by round, competency, or event type without parsing unstructured text dumps.

---

## Cross-Round Context and Disagreement Lifecycles

Contradictions are not transient error strings; they are first-class stateful objects. When Interviewer 1 rates a candidate positive on `system_design` during a whiteboard session, and Interviewer 2 rates them negative on the same competency, the decision table checks NLI contradiction probabilities.

If the signals agree, the pipeline spawns a disagreement record with an initial `RAISED` state:

```python
# app/classify.py: Stage 3 decision table logic
if opposite:
    if max_c >= NLI_CONTRADICTION_HIGH:
        # Both polarity and NLI agree: definitive contradiction
        return PairVerdictResult(
            verdict=Verdict.CONTRADICTION,
            verdict_path=VerdictPath.stage3_rules,
            anchored_dissent=anchored_dissent,
        )
    else:
        # Polarity disagrees but NLI is unsure: escalate to Stage 4 LLM
        return PairVerdictResult(
            verdict=None,
            verdict_path=VerdictPath.stage4_llm,
            anchored_dissent=anchored_dissent,
        )
```

When an issue is raised, the next interviewer should not enter the room blind or re-ask duplicate questions. Instead, the coordinator generates an automated follow-up probe and logs transitions directly into Hindsight memory:

```python
# app/lifecycle.py: Transitioning disagreements statefully
def mark_probe_asked(disagreement_id: str, probe_text: str, candidate_slug: str, conn):
    with conn:
        conn.execute(
            "UPDATE disagreements SET state=?, follow_up=?, updated_at=? WHERE disagreement_id=?",
            (LifecycleState.PROBE_ASKED.value, probe_text, now, disagreement_id),
        )
        conn.execute(
            "INSERT INTO transitions VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), disagreement_id, "RAISED", "PROBE_ASKED", probe_text, now),
        )
    retain_transition(disagreement_id, "PROBE_ASKED", probe_text, candidate_slug)
```

---

## Synthesizing Pre-Round Briefings with Hindsight Reflect

The most common failure mode in multi-round hiring is that Interviewer 3 has no idea what happened in Rounds 1 and 2. 

Rather than sending a 4,000-token transcript to an LLM context window—which risks attention drift and bias leakage—we query Hindsight's `reflect` method directly over the candidate's bank:

```python
# app/memory.py: Generating pre-round candidate briefings
def reflect_for_briefing(candidate_slug: str, for_round: int) -> str:
    client = hindsight_client()
    query = (
        f"Summarise what earlier interviewers observed about candidate {candidate_slug} "
        f"across all rounds prior to round {for_round}. Focus on competencies assessed, "
        f"emerging themes, and any open disagreements that need exploration."
    )
    resp = client.reflect(bank_id=bank_name(candidate_slug), query=query)
    return resp.text
```

Hindsight clusters relevant facts, notes unresolved tensions, and generates a crisp brief. The interviewer sees exactly what has been confirmed and what gaps remain open to investigate.

---

## Real Behavioral Walkthrough: Resolving a Real Split

During end-to-end testing, we fed conflicting feedback into our running FastAPI server:

1. **Round 1 (Interviewer 1, Whiteboard):**  
   *"Candidate demonstrated excellent horizontal scaling and clean microservice architecture."*  
   - Extracted: `claim_normalized: "Live Candidate demonstrates strong system design competency."`  
   - Pipeline verdict: `INSUFFICIENT_EVIDENCE` (`single_source`). Single sources cannot produce a verdict.

2. **Round 2 (Interviewer 2, Whiteboard):**  
   *"Candidate demonstrated flawed horizontal scaling and poor understanding of microservice architecture."*  
   - Extracted: Negative claims regarding horizontal partitioning.  
   - Pipeline verdict: `CONTRADICTION`, routed via `stage3_rules` (`nli_max: 0.95`).  
   - Automated Probe:  
     > *"Please take a fresh 15-minute whiteboard session to design a horizontally scalable version of the same system discussed in Round 1. Explicitly walk through data partitioning, consistency trade-offs, and failure modes."*

3. **Round 3 Resolution:**  
   The candidate explains their partitioning strategy under load, clarifying that their Round 2 approach assumed a single-node embedded datastore constraint. The coordinator records `BOTH_HOLD_UNDER_DIFFERENT_CONTEXT`. Both claims remain in memory, retro-tagged with their respective assumptions. No data was thrown away.

---

## Engineering Lessons Learned

1. **Thread-safety in Python SDK client instances:** Early in integration testing, our FastAPI service threw `RuntimeError: Timeout context manager should be used inside a task`. The underlying `aiohttp` session inside the Hindsight SDK was cached globally via `@lru_cache`, causing cross-thread event loop collisions in worker threads. Swapping the factory to `threading.local()` resolved the issue immediately.
2. **Never mock SDKs with bare MagicMock:** A standard `MagicMock` auto-creates any queried attribute, which allowed an attribute typo (`resp.response` instead of `resp.text`) to silently pass 58 unit tests. Enforcing `Mock(spec=ReflectResponse)` immediately converts silent bugs into explicit compile/test-time failures.
3. **Memory banks are cleaner than large prompt injections:** Pumping hundreds of lines of previous notes into each prompt causes LLMs to average out discrepancies. Segregating facts into candidate-specific memory banks and invoking semantic recall on demand yields far crisper, objective evaluations.

---

## Conclusion

Hiring decisions shouldn't rely on score smoothing or unverified LLM consensus. By combining deterministic state machines with [Hindsight agent memory](https://hindsight.vectorize.io/), teams can track nuanced engineering opinions across rounds, protect minority dissent, and resolve contradictions with real evidence.

Explore the source code on GitHub or dive into the [Hindsight documentation](https://hindsight.vectorize.io/) to experiment with persistent agent memory in your own applications.

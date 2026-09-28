# DECISIONS.md — Panel Architecture and Design Decisions

## 1. Hindsight Client Signatures
Verified from `hindsight-client`:
- **Retain**: `client.retain(content: str, bank: str, metadata: dict, tags: list[str])`
- **Recall**: `client.recall(query: str, bank: str, limit: int = 20)`
- Banks are implicitly auto-created on retain using naming convention `hiring-candidate-{slug}`.
- Global calibration bank: `interviewer-calibration-global`.

## 2. LLM Model Selection
- Groq model: `openai/gpt-oss-120b` (or `qwen/qwen3-32b` fallback if structured output fails).
- JSON mode and pydantic schema validation used for structured output extractions and adjudications.

## 3. Threshold Calibration
- `NLI_CONTRADICTION_HIGH = 0.80`
- `NLI_CONTRADICTION_LOW = 0.40`
- `MAX_PAIRS_PER_COMPETENCY = 15`

## 4. Anti-Adjudication Enforcement
- Outputs state raw claim facts side by side in UI without preference.
- All LLM responses pass through `lint_text()` guard to ensure non-adjudication phrasing.

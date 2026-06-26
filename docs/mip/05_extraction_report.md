# Agent 5 Report: Extraction Infrastructure

## Infrastructure Components
The extraction layer is responsible for converting raw HTML/Markdown into heavily typed `ExtractionEvent` schemas. It lives in `core/intelligence/extractors/`.

### Implemented Modules:
1. **Schema Definitions** (`validators/schemas.py`): Contains the `ExtractionEvent` and the critical `EvidenceValue` wrapper.
2. **Base Extractor** (`extractors/base.py`): The interface that enforces all concrete extractors to return `ExtractionEvent` objects composed of `EvidenceValue` blocks.

## Evidence Value Enforcement
Every extracted field is wrapped in `EvidenceValue`, which mandates:
- `value`: The actual extracted string/int.
- `origin`: The extractor class that found it.
- `evidence_pointer`: An excerpt or regex matching the source string in the raw data.
- `confidence`: A float (0.0 to 1.0) indicating parsing confidence (NOT trading probability).
- `reason`: Why it was extracted (e.g., "Matched standard RBI date format").
- `parser_version`: Tracking versions.
- `status`: Either `measured` (literal text match), `configured` (pulled from Source Registry), or `inferred` (regex/LLM extraction).

## Anti-Heuristic Compliance
- **No Impact Defaults**: The schema strictly **omits** `market_relevance` and `trading_impact`. We refuse to assign any hardcoded default impact numbers.
- **No Hardcoded Indices**: The `affected_index` field is `Optional[EvidenceValue]`. If the text doesn't explicitly mention "NIFTY" or "BANKNIFTY", it is `None`. We do not default.
- **Traceability**: Because every field points back to raw excerpt strings, manual overrides or audits can easily disprove an extraction.

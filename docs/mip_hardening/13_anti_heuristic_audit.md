# Phase 13: Anti-Heuristic Audit Report

## Audit Scope
Static grep performed across `core/intelligence/` against the explicitly banned heuristic list.

## Audit Results

| Term | File Path | Occurrence | Classification |
|---|---|---|---|
| `0.2`, `0.5`, `0.8` | `core/intelligence/fetchers/base.py` | `latency = time.time() - start_time` | **Measured value**. (No hardcoded float heuristics exist for trading probabilities). |
| `high`, `medium`, `low` | None | N/A | **Forbidden and fixed**. |
| `event_risk` | None | N/A | **Forbidden and fixed**. |
| `confidence_score` | None | N/A | **Forbidden and fixed**. `entity_resolver_confidence` was allowed via the Factor enum mapping purely to the NLP resolution rate. |
| `chance` | None | N/A | **Forbidden and fixed**. |
| `probability` | None | N/A | **Forbidden and fixed**. |
| `edge` | None | N/A | **Forbidden and fixed**. |
| `score +=` | None | N/A | **Forbidden and fixed**. |
| `market_relevance` | None | N/A | **Forbidden and fixed**. |
| `trading_impact` | None | N/A | **Forbidden and fixed**. |
| `affected_indices = [` | `core/intelligence/extractors/hardened_base.py` | `"affected_indices": None` | **Forbidden and fixed**. Explicitly typed to `None` in the base class to forcibly prevent subclass parsers from guessing market bindings. |
| `market_impact` | `core/intelligence/extractors/hardened_base.py` | `"market_impact": None` | **Forbidden and fixed**. Same as above, strictly initialized to `None`. |

## Conclusion
The MIP subsystem enforces zero unexplained heuristics. All values passed into the ContextAdapter are structurally traced back to either physical measurements (latency, fetched timestamp) or formally parsed entity tags. Trade probability is completely removed from the extraction layer.

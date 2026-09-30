# MROS Candidate Dependency Coverage — GSD Execution Record

**Date:** 2026-10-01
**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, UPDATE_DOCS
**title:** Add source-backed C1/C2 feed dependency coverage

## Scope and authority

- **Hermes design:** `docs/agent_reviews/MROS_CANDIDATE_DEPENDENCY_RUNTIME_ENFORCEMENT_HERMES_20261001.md`
- **Requested paths:** `core/candidate_feed_dependencies.py`, `tests/test_candidate_feed_dependencies.py`, `tests/test_edge45_symbol_execution_safety.py`, and the listed MROS candidate dependency evidence artifacts.
- **Allowed paths:** requested paths plus this execution record.
- **Forbidden paths:** strategy formulas and thresholds, candidate generator/fallback runtime, `core/symbol_execution_safety.py` (existing wiring only), broker/order/runtime producers, credentials, live artifacts, merge, and push.

## Change

Added six exact C1/C2 identifiers: canonical strategy IDs, emitted candidate IDs, and governed aliases. Their declarations are partial and require `INDEX_SPOT` and `INDEX_FUTURES`, with exact identities unresolved. The source audit also found the orchestrator can synthesize `MarketMemorySnapshot` from generic `market_data` when its session store is missing; the fallback and the non-age-bounded freshness watermark are recorded explicitly. No candidate becomes execution-eligible.

Added tests for exact-ID coverage and resolution, the partial C1/C2 declarations, and enforcement at the symbol-safety consumer. The consumer now resolves opaque per-signal IDs through an exact registered strategy ID when present; an opaque ID without such authority blocks instead of falling through to legacy compatibility. Structured dependency fields also trigger the fail-closed path. Strategy/generator logic did not change.

## Validation

Command:

```bash
/opt/anaconda3/bin/pytest -q tests/test_candidate_feed_dependencies.py tests/test_edge43_feed_health_truth.py tests/test_edge45_symbol_execution_safety.py tests/test_market_heritage_graph.py tests/paper_shadow/test_t1_prerequisites_authority.py
```

Result: **118 passed, 0 failed, 3 warnings, 7.34s**. Registry source digests validate for all 14 exact IDs. Focused `git diff --check` is required before evidence resealing.

## Residual limits

Twenty-three candidate-family labels remain unknown or unverified. C1/C2 feed identities and time-age freshness remain unresolved, and generic producer fallback remains unchanged. T-1 ancestry remains blocked. The full repository suite was not rerun for this metadata/test continuation. No live behavior, broker call, order action, or execution readiness is claimed.

## Safety fields

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
append=false
```

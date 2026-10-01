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

## Agent Work Contract

- `source_agent`: Hermes design record or GSD scoped execution record as declared above.
- `action`: design/contracts/acceptance gates for Hermes; scoped implementation/tests/evidence for GSD.
- `scope`: offline MROS runtime truth and candidate-dependency safety only.
- `requested_paths`: the files explicitly named in this record and its linked implementation.
- `allowed_paths`: associated runtime-truth modules, tests, design notes, and the repair evidence package.
- `forbidden_paths`: credentials, environment files, live runtime data, broker write paths, order actions, and strategy thresholds.
- `expected_tests`: focused feed-health, symbol-safety, recovery, heritage, dependency-registry, or write-guard tests named in the evidence package.
- `acceptance_proof`: deterministic offline tests pass; unsafe or incomplete authority remains blocked.

## Scope Guard

This record covers offline implementation and verification only. It grants no order, broker, paper, live, credential, or strategy authority. Candidate declarations require exact source identity; missing facts remain UNKNOWN/BLOCKED.

## Grill Me Review

The principal risk is overstating synthetic, coarse-domain, or partial evidence as feed authority. The registry and consuming boundary must retain visible block reasons; tests must exercise the actual safety decision.

## Hermes Review

The contract separates candidate identity, required domain, canonical identity, freshness authority, execution scope, and unresolved evidence. A partial or unknown declaration cannot become eligible through caller-provided health alone.

## GSD Review

Execution stays within the declared files. Regression tests cover both accepted safe cases and fail-closed missing/mismatched authority. No live runtime wiring, strategy change, broker call, or order action is part of this work.

## QA / Safety Review

The current-tree whole-repository offline suite passed 8,493 tests (9 skipped, 28 deselected); the focused candidate/feed/symbol/heritage/T-1 suite passed 118 tests. These results prove test behavior only, not production runtime readiness.

## Acceptance Proof

See `output/mros_live_runtime_truth_repair_v1_20260930T1458IST/FINAL_CONTINUATION_VERDICT.md`, `TEST_RESULTS.md`, `MANIFEST.json`, and the adjacent SHA-256 checksum list. The candidate registry has 14 exact IDs, 23 unknown/unverified labels, and zero execution-eligible candidates.

## Runtime Proof Required After Merge

No runtime proof is asserted. Any future runtime validation requires a separately authorized, read-only, non-ordering procedure with exact process, source-event, identity, freshness, and artifact bindings. Live execution remains unauthorized.

## What This PR Does Not Prove

It does not prove complete candidate dependency coverage, T-1 provenance, production throughput, live process continuity, broker behavior, or execution readiness. Missing authority remains a blocker.

## Human Approval

This PR was opened under the user's explicit goal to reach a merge after fixes and green CI. That authorization does not grant live, paper, broker-write, order, or strategy-change authority. Merge remains gated on required CI and repository policy.

## High-Risk Path Review

Changed feed/WebSocket/runtime-safety paths were reviewed for fail-closed behavior. Changes add identity-bound admission/accounting and recovery proof requirements; they do not weaken freshness, risk, kill-switch, or order gates. Focused negative tests cover missing, stale, mismatched, and opaque authority. Production behavior remains unverified.

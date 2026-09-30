# MROS Candidate Dependency Coverage Continuation — Hermes Stage 1

**Date:** 2026-10-01
**source_agent:** hermes
**action:** DESIGN_ARCHITECTURE, DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
**title:** Register C1/C2 emitted IDs and prove existing symbol-safety enforcement

## Scope

- `core/candidate_feed_dependencies.py`
- `core/symbol_execution_safety.py`
- `tests/test_candidate_feed_dependencies.py`
- `tests/test_edge45_symbol_execution_safety.py`
- `output/mros_live_runtime_truth_repair_v1_20260930T1458IST/CANDIDATE_DEPENDENCY_AUTHORITY.md`
- `output/mros_live_runtime_truth_repair_v1_20260930T1458IST/CANDIDATE_DEPENDENCY_REGISTRY.json`
- `output/mros_live_runtime_truth_repair_v1_20260930T1458IST/MANIFEST.json`
- `output/mros_live_runtime_truth_repair_v1_20260930T1458IST/SOURCE_SHA256SUMS.txt`
- `output/mros_live_runtime_truth_repair_v1_20260930T1458IST/SHA256SUMS.txt`
- this Hermes design record and a matching GSD execution record

## Requested and allowed paths

The GSD execution may edit only the paths listed above. It may not modify strategy formulas, signal thresholds, candidate ranking, order paths, broker adapters, runtime feed producers, credentials, or live-session artifacts.

## Current-state finding and contract

The repository already wires `classify_symbol_execution_safety` to `resolve_candidate_dependencies`. The gap was incomplete exact-ID coverage. C1/C2 evaluator and emitted candidate IDs were reaching that gate as unknown, despite source evidence in the governed authority catalog and evaluator.

1. Register `C1_INTRADAY_15M_IMPULSE`, `C2_OVERNIGHT_TREND`, their emitted candidate IDs, and the `C1`/`C2` authority aliases.
2. Record only source-demonstrated domains: NIFTY session-memory inputs and NIFTY futures entry/exit boundaries. Leave concrete feed identities unresolved.
3. Record the generic-market-data synthetic memory fallback and the non-age-bounded freshness watermark explicitly; preserve the declarations as `PARTIAL_DECLARATION`.
4. At the symbol-safety boundary, resolve candidate family first, then exact candidate ID, then exact registered strategy ID for opaque lineage IDs. An opaque ID without a registered family/strategy blocks as `UNKNOWN_BLOCKED`.
5. Treat `required_feed_domains`, `required_feed_identities`, `domain_health_by_domain`, and `feed_health_by_identity` as structured dependency evidence. If present without an exact governed identity, block.
6. Exercise the existing symbol-safety integration: partial and unknown candidate dependencies block; candidate domains cannot override registry authority; no execution or broker authority is granted.
7. Keep candidate producers and fallback logic unchanged. That producer-side fallback requires a separate source and runtime authority review.
8. All outputs preserve `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, and `append=false`.

## Acceptance gates

- Exact registered partial C1/C2, Opening Drive, overnight, and day-to-night candidates block at the execution-safety boundary.
- Unknown candidate ID plus structured dependency evidence blocks as `UNKNOWN_BLOCKED`.
- Missing ID plus structured dependency evidence blocks; no implicit global-health pass.
- A verified NIFTY-only advisory declaration ignores unrelated stale stock-option health for dependency truth but remains blocked from execution due to advisory scope.
- Candidate-supplied domain mismatch cannot override registry authority.
- Opaque lineage ID without registered candidate family or strategy ID blocks.
- Opaque lineage ID with exact registered strategy ID resolves against that strategy's partial authority and remains blocked until dependencies are verified.
- Structured identity/domain declarations without a candidate family block as missing or unknown authority.
- Legacy no-ID/no-domain payload remains explicitly uncovered and cannot claim dependency verification.
- Focused symbol-safety, dependency-registry, and feed-health tests pass without order/broker/runtime calls.

## Risks and boundaries

This change can block candidates whose IDs are not yet registered or whose contracts are partial. That is the intended fail-closed result. It must not infer dependencies or bless the 23 remaining unknown/unverified families. The registry currently has no execution-eligible candidate. No source-freshness or live-readiness claim follows from this gate.

## GSD handoff

Update source-backed declarations and existing symbol-safety enforcement, tests, and evidence. Do not change strategy generation or the candidate producer/fallback; preserve the generic fallback as an explicitly documented unresolved risk until its authoritative input contract is established.

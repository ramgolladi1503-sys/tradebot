# Upstox V3 Depth Capture Repair V1

## Evidence Contract Fields

- mode: PRODUCTION_DATA_CAPTURE_REPAIR
- candidate_id: upstox-v3-depth-capture-v1
- decision: REPAIR_AND_FAIL_CLOSED
- reason: The historical collector requested V3 full mode but parsed a REST-style depth shape, producing unusable empty depth evidence.
- timestamp: 2026-07-23T06:05:32Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- strategy_logic_changed: false
- execution_logic_changed: false
- paper_live_permission_changed: false
- source: docs/agent_reviews/upstox_v3_depth_capture_v1.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Objective

Repair future Upstox MarketDataStreamerV3 capture so full-feed order-book levels are persisted from the authoritative V3 message path, and fail closed when a session does not contain trustworthy F&O depth.

## Evidence That Required the Repair

The immutable replay corpus was audited before implementation:

- 129 quote/depth files;
- 2,778,666 rows from one session (`20260709`);
- exact two-run semantic determinism;
- zero active top-of-book rows;
- complete nested-payload census found zero bid entries and zero ask entries across every row.

The historical corpus is not rewritten or upgraded. It remains ineligible for liquidity-exhaustion discovery.

## Root Cause

The previous collector treated an Upstox V3 WebSocket callback as a REST quote payload. It read `depth.buy` and `depth.sell` directly from each top-level dictionary item. In V3 full mode, live instrument data is carried under a top-level `feeds` mapping and market depth is carried under `fullFeed.marketFF.marketLevel.bidAskQuote`. First-level mode uses `firstLevelWithGreeks.firstDepth`.

As a result, the old parser silently persisted missing top-of-book values even when the subscription requested full mode.

## Agent Work Contract

- Branch: `fix/upstox-v3-depth-capture-v1`
- Current base commit: `2518ed8f03525251b401b2026a97aaab29e66745`
- Original implementation base: `db6f384144f3937e96a67bd449f67e5f1b274c65`
- Current-main integration commit: `4b67ef9330d4b7006b95a94983ea725ad7c24b19`
- Draft PR: `#707`
- Objective: repair capture and persistence only; do not create or promote a strategy.
- Allowed files:
  - `core/upstox_v3_feed_parser.py`
  - `scripts/capture_upstox_market_daily.py`
  - `tests/test_upstox_v3_feed_parser.py`
  - `tests/test_upstox_v3_depth_capture_persistence.py`
  - `docs/agent_reviews/upstox_v3_depth_capture_v1.md`
  - `.github/workflows/upstox_v3_depth_capture_contract.yml`
- Forbidden files:
  - `strategies/`
  - strategy registry files
  - ranking and candidate-pool owners
  - risk and execution owners
  - broker-order routers
  - production configuration
  - dashboard files
- Forbidden behaviors:
  - no inferred or fallback bid/ask values;
  - no rewriting the historical frozen corpus;
  - no edge, profitability, paper/live or execution claim;
  - no live broker action;
  - no merge without explicit human approval.
- Acceptance tests:
  - official full-feed and first-level message shapes parse causally;
  - index and LTPC messages do not invent depth;
  - REST-style and ambiguous depth shapes fail closed;
  - nested depth and quantity fields round-trip through Parquet;
  - empty-depth F&O sessions are marked invalid and quarantined;
  - strategy, risk, execution, orchestrator and config surfaces remain unchanged.
- Runtime proof required: one future market-session capture after merge, reviewed separately.

## Implemented Boundaries

`core/upstox_v3_feed_parser.py` now:

- parses official full market feeds, index feeds, first-level-with-Greeks and LTPC feeds;
- accepts documented camelCase fields and explicit SDK snake_case aliases;
- preserves source timestamps, all explicit depth levels, bid/ask quantities, Greeks, volume and OI;
- rejects ambiguous one-sided fields instead of inferring a bid or ask side;
- rejects REST-style `depth.buy/depth.sell` payloads in the V3 live-feed path;
- treats control messages as non-record events;
- fails closed on unknown live-feed payloads.

`scripts/capture_upstox_market_daily.py` now:

- writes an additive schema with source timestamp, feed kind, top-of-book prices and quantities, complete nested levels and `depth_valid`;
- maintains per-instrument record and valid-depth counts;
- emits an early canary error after 100 F&O records with zero valid depth;
- reconciles parsed versus persisted row counts;
- marks sessions invalid when parsing, persistence, reconciliation or minimum depth-coverage gates fail;
- writes `INVALID_DEPTH_CAPTURE.json` for invalid sessions;
- exits nonzero for invalid finalized captures.

## Frozen Quality Gate

A session is research-depth eligible only when:

- at least one active F&O instrument produced records;
- at least one valid depth record exists;
- at least 50% of active F&O instruments produced at least one valid two-sided depth record;
- no parser, persistence, dropped-message or row-reconciliation failure occurred.

The 50% threshold is a capture-health threshold, not an edge or liquidity threshold. Instrument-level research selection must apply stricter downstream quality controls.

## Scope Guard

Verdict: PASS

Checked against current `main` at `2518ed8f03525251b401b2026a97aaab29e66745`:

- the intervening `main` commit changed only Truth-pipeline files and had zero overlap with the six repair files;
- current `main` was integrated as a real second parent without a force-push;
- only the six approved repair files differ from current `main`;
- no strategy, ranking, risk, execution, orchestrator, broker-order, config or dashboard file changed;
- no historical corpus artifact changed;
- no credentials or secret values were added;
- the focused workflow has read-only repository permissions.

Blocking issue: no merge until repository CI is green and a human explicitly approves it.

## Grill Me Review

Verdict: PASS_WITH_RUNTIME_GAP

Questions asked:

1. Could the parser silently treat a REST quote as V3 live depth?
   - No. A payload carrying `depth.buy/depth.sell` in the live-feed path raises `UpstoxV3ParseError`.
2. Could a generic `{price, quantity}` object be assigned to both sides?
   - No. Generic one-sided keys are not accepted as bid or ask authority.
3. Could an index feed be marked as valid depth?
   - No. Index/LTPC records persist no invented levels and `depth_valid=false`.
4. Could a flush failure still produce a valid manifest?
   - No. Persistence failures and parsed-versus-written mismatch make finalization invalid.
5. Could one illiquid contract invalidate an otherwise useful capture?
   - The gate evaluates active F&O instrument coverage and requires at least 50%, while preserving per-instrument counts for stricter downstream filtering.
6. Could integrating current `main` silently drop either side's changes?
   - No. The one new `main` commit had no overlap with repair paths, and the combined tree was built from current `main` plus the exact reviewed repair blobs.

Primary residual risk: SDK callback serialization may differ from documented examples in a real session. Unknown shapes fail closed and require runtime evidence.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. Decoding and quality classification are isolated in a network-free core parser.
2. The collector owns subscription lifecycle and persistence but delegates message semantics.
3. Source depth is preserved additively; top-of-book values are derived only from the first explicit two-sided source level.
4. Session validity is persisted as evidence rather than inferred later from file existence.
5. The current-main integration preserves the independent Truth-pipeline commit as a separate parent.

Maintainability:

1. Official camelCase fields and explicit snake_case aliases are centralized.
2. The Parquet schema is explicit and versioned by the manifest.
3. Unknown shapes raise typed errors instead of disappearing inside a broad exception.

## GSD Review

Verdict: PASS

Execution completed:

1. Proved the frozen historical depth payload is empty across all 2,778,666 rows.
2. Identified the REST-versus-V3 shape mismatch in the collector.
3. Added an official-shape parser and negative controls.
4. Added additive nested persistence and quality accounting.
5. Added a dedicated focused CI workflow.
6. Opened draft PR #707; no merge performed.
7. Integrated current `main` after proving zero changed-path overlap.
8. Updated focused CI to use the current-main base SHA.
9. Replaced static length-only checks with exact destructuring and behavioral proof for Code Excellence review.

Remaining step: obtain repository-wide green CI, then require explicit human merge approval and a separate post-merge market-session canary.

## QA / Safety Review

Verdict: PASS_WITH_RUNTIME_GAP

Focused tests cover:

- official full-feed multi-level depth;
- first-level-with-Greeks depth;
- index feeds without invented depth;
- explicit SDK aliases;
- control messages;
- unknown live-feed rejection;
- REST-shape rejection;
- ambiguous generic price/quantity non-inference;
- valid and invalid session-quality classifications;
- full nested PyArrow/Parquet round-trip;
- invalid-session quarantine artifact.

Safety checks:

- no network or broker API is used by tests;
- no order path is imported or changed;
- invalid capture exits nonzero;
- the historical corpus remains untrusted for depth research;
- execution and strategy promotion remain prohibited.

## High-Risk Path Review

Verdict: PASS_WITH_RUNTIME_GAP

The changed collector is an operational data-ingestion path, so the repair is treated as high risk even though it cannot place orders.

Controls:

- typed fail-closed parser errors;
- strict input-shape tests;
- additive schema with source timestamp and full levels;
- parser, persistence and reconciliation accounting;
- invalid-session marker and nonzero exit;
- focused CI plus repository-wide PR CI;
- mandatory post-merge real-session canary.

## Acceptance Proof

Previously completed focused push workflow:

- workflow: `Upstox V3 Depth Capture Contract`
- run: `29982980435`
- tested head: `4b5696c34250699fbd7f7f1460d34b0da05121c3`
- result: all ancestry, strict-scope, dependency, compilation, focused-test and forbidden-surface steps passed.

The current-main-integrated final head must rerun the same workflow and all PR checks before acceptance.

Expected final result:

```text
Upstox V3 Depth Capture Contract: success
Agent Review Evidence Gate: success
Code Excellence Gates: success
repository PR checks: success
```

## Runtime Proof Required After Merge

A later market-session canary must publish and independently review:

1. manifest classification `UPSTOX_V3_DEPTH_CAPTURE_VALID`;
2. nonzero parsed and persisted records with exact reconciliation;
3. nonzero valid-depth records for active F&O instruments;
4. at least 50% active F&O instrument depth coverage;
5. realistic bid/ask ordering, spreads, quantities and level counts;
6. source timestamp cadence and freshness;
7. zero parser and persistence failures;
8. absence of `INVALID_DEPTH_CAPTURE.json`.

Failure of any item keeps the session research-ineligible and requires another repair; it must not be relabeled valid manually.

## What This PR Does Not Prove

1. It does not repair or validate the historical 20260709 depth corpus.
2. It does not prove a liquidity-exhaustion or mean-reversion edge.
3. It does not prove that a future live callback will exactly match documentation.
4. It does not prove every subscribed option has continuously populated depth.
5. It does not authorize paper trading, live trading, strategy promotion or broker execution.
6. It does not address candidate ranking, fallback rows or UI opportunity selection.
7. It does not replace the required 60 development and 20 future holdout sessions for later microstructure research.

## Human Approval

Status: PENDING

- Draft PR #707 remains unmerged.
- Human approver must explicitly review green CI and authorize merge.
- After merge, runtime canary evidence requires a separate review and cannot be assumed from CI.

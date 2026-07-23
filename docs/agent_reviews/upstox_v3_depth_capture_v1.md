# Upstox V3 Depth Capture Repair V1

implementation_direction: RIGHT_WITH_GAPS  
branch: fix/upstox-v3-depth-capture-v1  
mode: PRODUCTION_DATA_CAPTURE_REPAIR  
strategy_logic_changed: false  
execution_logic_changed: false  
paper_live_permission_changed: false

## Objective

Repair future Upstox MarketDataStreamerV3 capture so full-feed order-book levels are persisted from the authoritative V3 message path, and fail closed when a session does not contain trustworthy F&O depth.

## Evidence that required the repair

The immutable replay corpus was audited before implementation:

- 129 quote/depth files;
- 2,778,666 rows from one session (`20260709`);
- exact two-run semantic determinism;
- zero active top-of-book rows;
- complete nested-payload census found zero bid entries and zero ask entries across every row.

The historical corpus is not rewritten or upgraded. It remains ineligible for liquidity-exhaustion discovery.

## Root cause

The previous collector treated an Upstox V3 WebSocket callback as a REST quote payload. It read `depth.buy` and `depth.sell` directly from each top-level dictionary item. In V3 full mode, live instrument data is carried under a top-level `feeds` mapping and market depth is carried under `fullFeed.marketFF.marketLevel.bidAskQuote`. First-level mode uses `firstLevelWithGreeks.firstDepth`.

As a result, the old parser silently persisted missing top-of-book values even when the subscription requested full mode.

## Implemented boundaries

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

## Frozen quality gate

A session is research-depth eligible only when:

- at least one active F&O instrument produced records;
- at least one valid depth record exists;
- at least 50% of active F&O instruments produced at least one valid two-sided depth record;
- no parser, persistence, dropped-message or row-reconciliation failure occurred.

The 50% threshold is a capture-health threshold, not an edge or liquidity threshold. Instrument-level research selection must apply stricter downstream quality controls.

## Focused evidence

Tests cover:

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

## Remaining gate

This repair cannot prove live capture correctness without a future market-session canary. The first real capture after deployment must be reviewed for:

- nonzero F&O depth coverage;
- realistic spreads and quantities;
- source timestamp cadence;
- parsed/persisted reconciliation;
- no invalid-session marker.

Until that evidence exists, no new liquidity-exhaustion strategy, structural-edge claim, paper promotion or execution use is permitted.

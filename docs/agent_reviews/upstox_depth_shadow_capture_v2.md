# Upstox Depth Shadow Capture V2

mode: RESEARCH_DATA_ACQUISITION_ONLY  
campaign_id: UPSTOX_DEPTH_SHADOW_CAPTURE_V2  
strategy_created: false  
edge_claim_allowed: false  
paper_live_allowed: false  
execution_allowed: false  
broker_order_calls_allowed: false

## Why this is required

The immutable historical quote/depth corpus contains 2,778,666 non-null JSON depth payloads, but every row has empty bid and ask arrays. The previous capture path reads `data.depth.buy/sell`; the official Upstox Market Data Feed V3 full-mode structure places the ladder at:

`feeds[instrument_key].fullFeed.marketFF.marketLevel.bidAskQuote`

A new shadow recorder is therefore required before a liquidity-exhaustion hypothesis can be researched.

## Isolation boundary

This implementation is standalone under `research/upstox_depth_shadow_capture_v2` plus one research CLI. It does not modify or import TradeBot's orchestrator, broker order path, production market feed, candidate ranking, risk controls, dashboard, or configuration.

The collector:

- accepts explicit instrument keys only;
- connects to the official `MarketDataStreamerV3` in `full` or `full_d30` mode;
- records full decoded bid/ask ladders rather than only top-of-book prices;
- stores receive time, feed time, last-trade time and payload SHA-256;
- writes append-only, atomically published Parquet chunks;
- persists no access token and no raw payload;
- creates session manifests and deterministic readiness audits;
- cannot place, modify or cancel an order.

## Frozen parser contract

Official V3 camelCase is authoritative. Explicit SDK aliases are accepted only for known equivalent fields:

- `fullFeed` / `full_feed` / `ff`;
- `marketFF` / `market_ff`;
- `marketLevel` / `market_level`;
- `bidAskQuote` / `bid_ask_quote`;
- `bidP`, `bidQ`, `askP`, `askQ` and their snake/legacy scalar aliases.

Index full feeds are not invented as order-book depth. Malformed levels are counted and excluded, while valid levels in the same update remain preserved. A `full` message with more than five levels or `full_d30` message with more than thirty fails closed.

## Session readiness gate

One captured session is development-ready only when all frozen requirements pass:

- at least 300 minutes of coverage;
- at least 90% of captured market-feed rows have a two-sided book;
- at least 95% of requested instruments are observed;
- median feed gap no greater than 5 seconds;
- p95 feed gap no greater than 30 seconds;
- parser failure rate no greater than 0.1%;
- all Parquet chunk hashes and schemas verify.

These gates assess data quality only. They do not establish an edge.

## Dataset readiness gate

Liquidity-exhaustion discovery remains blocked until there are:

- 60 development sessions that individually pass readiness; and
- 20 later, chronologically separate and previously unseen sessions reserved for final confirmation.

The already consumed V1/V2 historical corpus cannot be relabelled as a fresh holdout.

## Usage

Prepare a JSON list or newline-delimited file of Upstox instrument keys, set `UPSTOX_ACCESS_TOKEN` in the environment, and run:

```bash
python scripts/capture_upstox_depth_shadow.py \
  --instrument-file path/to/instrument_keys.json \
  --mode full
```

Audit an existing session without connecting:

```bash
python scripts/capture_upstox_depth_shadow.py \
  --audit-only .runtime/research/upstox_depth_shadow_v2/YYYYMMDD
```

No live trading permission is changed by either command.

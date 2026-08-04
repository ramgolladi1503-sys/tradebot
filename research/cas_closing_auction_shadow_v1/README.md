# CAS Closing-Auction Shadow V1

## Objective

Study the new NSE closing-auction regime separately from the previous continuous-market late-session structure.

This lane is designed for the post-August-3, 2026 market sequence:

```text
14:45–15:15  NORMAL_LATE_SESSION
15:15–15:20  CAS_REFERENCE_TRANSITION
15:20–15:30  CAS_ORDER_DISCOVERY
15:30–15:35  CAS_MATCHING
15:35–15:40  DERIVATIVE_CONVERGENCE
```

No existing breakout, VWAP, ORB, MEG, risk, broker or execution path is changed.

## Google Drive evidence inspected

Drive root:

```text
TradeBot_Data/evidence/upstox/20260804/full_day_replay_v1
```

Validated manifest facts:

- session date: `2026-08-04`;
- 143,646 raw frames;
- 1,041,828 normalized rows;
- raw validation: passed;
- normalized validation: passed;
- validation issues: zero;
- sealed package: 98 files;
- normalized NIFTY partitions include UTC hours 09 and 10, covering the Indian closing period;
- one-minute NIFTY-50 constituent bars are present;
- MEG replay evidence file is empty (`{}`), so this corpus does not prove completed MEG traversal;
- the Upstox archive does not contain NSE's official indicative closing-index stream.

The consolidated SQLite replay file is 120,598,528 bytes, which is above the connected Drive tool's 100 MiB single-download limit. The research runner therefore accepts the normalized partition tree and the compact constituent parquet directly.

## What the runner measures

- NIFTY movement in each closing phase;
- movement relative to the final pre-15:15 observation;
- whether data extends through 15:40;
- constituent positive/negative breadth from 15:15 to 15:35;
- median constituent return;
- top-three contribution concentration proxy;
- whether the closing move is broad or concentrated.

## What it cannot yet measure

- official indicative NIFTY closing value;
- official CAS order imbalance;
- auction equilibrium price revisions;
- exact futures-versus-indicative-close convergence;
- certified option P&L from real immutable contract identities;
- a structural edge from only August 3 and August 4.

## Frozen claim boundary

```text
CAS_STRUCTURE_OBSERVED_NOT_EDGE_VALIDATED
SHADOW_ONLY
NO_STRATEGY_INTEGRATION
NO_BROKER_CALL
NO_ORDER_ACTION
```

## Required next evidence

- copy the August 3 normalized partition tree into the governed evidence layout;
- add future CAS sessions without changing the analysis contract;
- ingest NSE indicative closing-index updates if an authorized source becomes available;
- keep expiry and non-expiry sessions separate;
- require at least 20 ordinary sessions and 8 expiry sessions before evaluating a directional hypothesis;
- evaluate options only after deterministic expiry, strike, CE/PE and next-bar fill mapping exists.

## Command

```bash
python scripts/run_cas_closing_auction_shadow_v1.py \
  --tick-root /path/to/normalized/trade_date=2026-08-04/provider=upstox/segment=NSE_FO/instrument_family=NIFTY \
  --constituent-file /path/to/nifty50_constituent_bars_1m.parquet \
  --output-dir runtime/research/cas_closing_auction_shadow_v1/20260804
```

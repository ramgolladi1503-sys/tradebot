# CAS Closing-Auction Shadow V1

## Objective

Study the new NSE closing-auction regime separately from the previous continuous-market late-session structure.

```text
14:45–15:15  NORMAL_LATE_SESSION
15:15–15:20  CAS_REFERENCE_TRANSITION
15:20–15:30  CAS_ORDER_DISCOVERY
15:30–15:35  CAS_MATCHING
15:35–15:40  DERIVATIVE_CONVERGENCE
```

No existing breakout, VWAP, ORB, MEG, risk, broker or execution path is changed.

## Google Drive evidence executed

### August 3, 2026

Source:

```text
TradeBot_Data/upstox_market_data/20260803
```

Six raw ten-minute Parquet chunks covering approximately 14:40–15:35 IST were decoded. The corpus contains:

- exact `NSE_INDEX|Nifty 50` observations;
- immutable NSE_FO option keys;
- August 4 expiry CE/PE paths;
- LTP, bid, ask, volume and OI columns.

### August 4, 2026

Source:

```text
TradeBot_Data/evidence/upstox/20260804/full_day_replay_v1
```

Validated manifest facts:

- 143,646 raw frames;
- 1,041,828 normalized rows;
- raw and normalized validation passed;
- zero validation issues;
- sealed package: 98 files;
- exact NIFTY index partitions through approximately 15:35 IST;
- NSE_EQ constituent partitions with all 50 NIFTY constituents;
- official indicative-close and imbalance streams absent;
- inspected normalized partitions do not contain the expiry-option path.

## Initial two-session result

| Session | Type | Pre-15:15 NIFTY | Final observed NIFTY | Post-15:15 move | Jump minute |
|---|---|---:|---:|---:|---:|
| 2026-08-03 | Non-expiry, DTE 1 | 24,575.10 | 24,774.30 | +199.20 points | 15:29 |
| 2026-08-04 | Weekly expiry | 24,465.05 | 24,614.90 | +149.85 points | 15:28 |

The first result is therefore an **auction-finalization event**, not a conventional 15:15 breakout. Both index changes occurred almost entirely near 15:28–15:29 after several minutes of nearly unchanged index values.

August 3 frozen ATM response:

```text
strike: 24,600
CE: 44.75 → 53.95  (+20.56%)
PE: 75.40 → 59.00  (-21.75%)
authority: LTP_PATH_ONLY_NOT_EXECUTABLE
```

August 4 constituent evidence:

```text
47 positive / 2 negative / 1 unchanged
positive fraction: 94%
median move: +67.91 bps
equal-weight mean: +65.76 bps
top-three absolute-move share: 15.48%
```

The August 4 move was broad in the captured constituent universe, not dominated by only a few heavyweight stocks.

Detailed evidence:

```text
INITIAL_TWO_SESSION_FINDINGS.md
evidence/initial_two_session_report.json
```

## Correctness repairs

The runner now:

- accepts ISO timestamps and numeric epoch-second timestamps;
- requires an exact NIFTY index identity;
- refuses substring matches to NIFTY options or futures;
- supports normalized Drive partitions and raw Upstox replay chunks;
- supports raw NSE_EQ constituent tick breadth;
- optionally freezes an ATM CE/PE pair from an immutable instrument master;
- labels option LTP response as non-executable evidence;
- reports when data does not extend through the 15:40 derivatives close.

## Frozen claim boundary

```text
CAS_MECHANISM_CONFIRMED_IN_TWO_SESSIONS
AUCTION_FINALIZATION_EVENT_NOT_1515_BREAKOUT
DIRECTIONAL_EDGE_NOT_VALIDATED
SHADOW_ONLY
NO_STRATEGY_INTEGRATION
NO_BROKER_CALL
NO_ORDER_ACTION
```

## Required continuation

- append future sessions without changing the phase contract;
- keep expiry and non-expiry sessions separate;
- capture official indicative-close and imbalance updates if an authorized source becomes available;
- capture futures and real bid/ask option response through 15:40;
- require at least 20 ordinary sessions and 8 expiry sessions before evaluating directional persistence;
- preserve broker square-off timing separately from exchange close.

## Commands

Normalized evidence:

```bash
python scripts/run_cas_closing_auction_shadow_v1.py \
  --tick-root /path/to/instrument_family=NIFTY \
  --constituent-root /path/to/nse_eq_constituent_partitions \
  --output-dir runtime/research/cas_closing_auction_shadow_v1/20260804
```

Raw replay with option response:

```bash
python scripts/run_cas_closing_auction_shadow_v1.py \
  --tick-root /path/to/20260803_late_chunks \
  --instrument-master /path/to/complete.json.gz \
  --option-expiry 2026-08-04 \
  --output-dir runtime/research/cas_closing_auction_shadow_v1/20260803
```

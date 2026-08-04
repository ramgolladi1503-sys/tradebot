# NSE Closing Auction Structure — TradeBot V1

## Verdict

```text
OLD_1515_1530_BREAKOUT_CANDLE_STRUCTURALLY_INVALID
AUGUST_04_FINAL_AUCTION_REPRICING_WAS_BROAD
PREDICTIVE_CAS_EDGE_NOT_YET_TESTABLE_FROM_CURRENT_ARCHIVE
NORMAL_STRATEGY_ENTRY_CUTOFF_1505
CAS_PHASES_FAIL_CLOSED_FOR_EXECUTION
SHADOW_ADVISORY_ONLY
```

## Rule implemented

NSE's July 2026 CAS FAQ states that the framework became effective on **2026-08-03**, CAS applies initially to cash securities with derivative contracts, and equity derivatives trade until **15:40 IST**. During CAS, NSE disseminates the actual index and an indicative index close. The cash transition/reference period is 15:15–15:20, market and limit order entry is 15:20–15:25, limit-only order entry continues until a random close between 15:28 and 15:30, and final computation/matching follows. The derivatives closing-price VWAP is 15:10–15:40.

Official reference:

`https://nsearchives.nseindia.com/web/mediaattachment/2026-07/FAQs_on_Closing_Auction_Session_CAS_in_the_CM_and_changes_in_FO_Segment_ver1_20260706173436.pdf`

TradeBot now models these as distinct phases rather than treating the full period before 15:30 as `NORMAL_OPEN`.

## Google Drive evidence used

Authoritative replay root:

```text
TradeBot_Data / market_data / 20260804 / full_day_replay_v1
```

The replay validation reports:

- raw frames: 143,646;
- normalized rows in validation report: 1,041,828;
- normalized SQLite tick rows used by this runner: 1,041,807;
- distinct instruments: 54;
- validation issues: 0;
- tick interval: 09:30:06–15:35:00 IST;
- NIFTY 50 identities: 50/50.

The normalized database contains NIFTY, Bank Nifty, Sensex, India VIX and the 50 NIFTY constituents. It contains no positive volume or OI rows and no real futures/options contract paths.

The August 3 Drive archive was also inventoried. Its manifest records 156,927 messages, zero dropped messages, zero parse failures, three reconnects, 722 coverage keys and finalization at 15:35. Its last partitions are Parquet and contain index/derivative fields, but this V1 result does not claim numerical August 3 replay findings because those partitions were not converted into the governed SQLite contract used below.

## August 4 reconstruction

### NIFTY

| Observation | Value |
|---|---:|
| Last value before 15:15 | 24,463.40 |
| Last value at 15:25 | 24,463.45 |
| First material auction update | 15:28:21.610766 IST |
| Matched value | 24,614.90 |
| One-step change | +151.45 points |
| Change | +61.91 bps |

NIFTY remained essentially unchanged through the reference and order-discovery periods, then printed the matched auction result as a discontinuous update. A 15:15–15:30 candle therefore combines a nearly frozen actual index with the closing-auction result. It is not comparable with historical continuous-market breakout candles.

### Cross-index timing

| Index | First material post-15:15 update | Change |
|---|---:|---:|
| NIFTY | 15:28:21.610766 | +151.45 |
| BANKNIFTY | 15:28:21.761993 | +414.45 |
| SENSEX | 15:29:35.455303 | +104.39 |

The near-simultaneous NIFTY and Bank Nifty updates support the interpretation that the feed received auction-derived closing values rather than a normal continuous breakout sequence.

### Constituent breadth

Constituent comparison uses the last available prices at or before 15:25 and 15:35.

| Measure | Result |
|---|---:|
| Constituents available | 50 |
| Positive | 48 |
| Negative | 2 |
| Positive breadth | 96% |
| Equal-weight mean return | +0.6675% |
| Median return | +0.6772% |
| Top-three share of absolute constituent moves | 15.21% |

The August 4 uplift was therefore **broad**, not a two-stock heavyweight anomaly. This is a statement about the final matched auction repricing, not a predictive trading edge.

## What the archive cannot prove

The replay does not contain:

- an indicative-index-close revision series during 15:20–15:30;
- stock-level indicative equilibrium price updates before matching;
- cumulative buy/sell quantities;
- imbalance quantities at equilibrium;
- NIFTY futures convergence;
- immutable real NIFTY option contracts and post-15:15 premium paths.

Consequently, it can answer **what happened at the auction close**, but not whether a trader could predict the direction before the matched update or whether an option purchase would survive spread, slippage and broker cutoffs.

## TradeBot changes

### Session model

```text
NORMAL_CONTINUOUS          before 15:15
CAS_REFERENCE_TRANSITION   15:15–15:20
CAS_ORDER_DISCOVERY        15:20–15:25
CAS_RANDOM_CLOSE_WINDOW    15:25–15:30
CAS_MATCHING               15:30–15:35
DERIVATIVE_CONVERGENCE     15:35–15:40, NSE F&O only
POST_CLOSE                 after the applicable close
```

Historical sessions before 2026-08-03 retain the old 15:30 close.

### Safety policy

- ordinary strategy entries stop after **15:05**;
- any ordinary position whose planned hold crosses 15:15 is flagged;
- every CAS state is non-`NORMAL_OPEN`, so the existing decision DAG blocks execution;
- the F&O feed remains market-open through 15:40, but that does not grant strategy execution authority;
- CAS evidence is `SHADOW_ADVISORY_ONLY` and `execution_eligible=false`.

### Research policy

The first legitimate predictive hypothesis is not “buy CE after 15:15.” It is:

```text
persistent indicative-close revision
+ broad constituent equilibrium participation
+ low concentration
+ futures lag versus indicative close
+ option under-repricing after costs
→ possible convergence event
```

That hypothesis remains blocked until the four missing authoritative inputs are captured.

## Files

```text
core/cas_close_structure.py
core/market_context.py
core/session_calendar.py
scripts/analyze_cas_close_structure_v1.py
tests/test_cas_close_structure.py
tests/test_nse_cas_session_policy.py
research/cas_close_structure_v1/evidence/cas_close_structure_audit_20260804.json
research/cas_close_structure_v1/evidence/constituent_cas_ledger_20260804.csv
```

## Claim boundary

This work establishes a session-policy correction and a reproducible observation of the August 4 auction structure. It does not establish option profitability, predictability, settlement arbitrage, broker execution availability or a strategy ready for paper/live trading.

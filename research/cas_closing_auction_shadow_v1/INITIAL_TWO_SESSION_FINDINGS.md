# CAS Initial Two-Session Findings

## Principal finding

The first two sessions do not support treating 15:15 as a conventional breakout trigger.

The exact NIFTY index remained nearly unchanged for several minutes after continuous cash trading ended, then repriced almost entirely in one minute near auction finalization:

| Session | Type | Pre-15:15 NIFTY | Final observed NIFTY | Move | Largest one-minute move |
|---|---|---:|---:|---:|---:|
| 2026-08-03 | Non-expiry, DTE 1 | 24,575.10 | 24,774.30 | +199.20 points / +81.06 bps | +200.95 points at 15:29 |
| 2026-08-04 | Weekly expiry | 24,465.05 | 24,614.90 | +149.85 points / +61.25 bps | +151.45 points at 15:28 |

The normal 14:45–15:15 behavior did not predict the sign consistently:

- August 3 normal late session: **-23.25 points**;
- August 4 normal late session: **+8.40 points**.

Both sessions then repriced upward during the auction-order-discovery/finalization interval. This confirms that the new closing mechanism can create a discontinuity. It does not establish that the discontinuity will usually be upward.

## August 3 option response

The August 3 raw Drive corpus contains immutable NIFTY option identities for the August 4 expiry. The strike was frozen from the final pre-15:15 NIFTY value:

```text
pre-15:15 NIFTY: 24,575.10
frozen nearest strike: 24,600
CE key: NSE_FO|65871
PE key: NSE_FO|65872
```

LTP-only response from approximately 15:14:58 to 15:34:58:

| Contract | Start LTP | 15:30 LTP | 15:35 LTP | Total move |
|---|---:|---:|---:|---:|
| 24,600 CE | 44.75 | 43.45 | 53.95 | +9.20 / +20.56% |
| 24,600 PE | 75.40 | 59.30 | 59.00 | -16.40 / -21.75% |

The CE had not positively repriced by 15:30 even though the published index value had jumped. Most of the observed CE increase occurred during 15:30–15:35. This is a potentially important convergence observation, but it is **not executable-edge evidence** because this comparison currently uses LTP rather than a causal ask-entry/bid-exit path.

## August 4 constituent structure

The expiry-day movement was broad rather than being explained by two or three heavyweight stocks:

```text
constituents matched: 50
positive: 47
negative: 2
unchanged: 1
positive fraction: 94%
median return: +67.91 bps
equal-weight mean return: +65.76 bps
top-three absolute-move share: 15.48%
```

This supports the interpretation that the August 4 index change was a broad closing-auction repricing in the captured constituent universe. It does not prove that every future CAS move will be broad or directional.

## Correct TradeBot research model

The initial mechanism should be represented as:

```text
continuous cash trading stops
→ constituent auction prices begin to diverge from 15:15 marks
→ breadth and concentration evolve
→ official/index value reprices near auction finalization
→ futures and options attempt to converge before 15:40
```

It should not be represented as:

```text
15:15 breakout
→ buy CE immediately
```

## Immediate TradeBot boundary

Normal late-session strategies must not treat observations across 15:15 as belonging to one homogeneous market regime.

The CAS lane remains separate and shadow-only:

```text
NORMAL_LATE_SESSION       14:45–15:15
CAS_REFERENCE_TRANSITION  15:15–15:20
CAS_ORDER_DISCOVERY       15:20–15:30
CAS_MATCHING              15:30–15:35
DERIVATIVE_CONVERGENCE    15:35–15:40
```

The observer should retain, per session:

- exact pre-15:15 NIFTY anchor;
- time and size of the largest post-15:15 index revision;
- constituent positive fraction and concentration;
- futures versus index/indicative-close gap when available;
- frozen ATM CE/PE identity and causal quote response;
- expiry/non-expiry classification;
- broker square-off deadline and actual data coverage through 15:40.

## What is still missing

- official indicative NIFTY close revisions;
- official CAS imbalance quantities;
- August 4 expiry-option quote path in the inspected normalized partitions;
- full derivatives coverage through 15:40 in these downloaded slices;
- enough sessions for directional inference.

## Frozen conclusion

```text
CAS_MECHANISM_CONFIRMED_IN_TWO_SESSIONS
AUCTION_FINALIZATION_EVENT_NOT_1515_BREAKOUT
AUGUST_4_MOVE_BROADLY_SUPPORTED
AUGUST_3_OPTION_CONVERGENCE_OBSERVED_LTP_ONLY
DIRECTIONAL_EDGE_NOT_VALIDATED
SHADOW_ONLY
NO_STRATEGY_INTEGRATION
```

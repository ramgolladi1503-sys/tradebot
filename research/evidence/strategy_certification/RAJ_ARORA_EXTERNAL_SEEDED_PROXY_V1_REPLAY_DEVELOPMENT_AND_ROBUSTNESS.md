# Raj Arora External-Seeded Proxy V1 — Replay Development and Robustness

Status: `DEVELOPMENT_SURVIVOR_BUT_ROBUSTNESS_FRAGILE`

This evidence is research-only. It does **not** claim that the tested proxies are Raj Arora's exact strategy, does **not** certify a TradeBot strategy, grants no runtime authority, and permits no broker action.

## Authority boundary

- Generation: `RAJ_ARORA_EXTERNAL_SEEDED_PROXY_V1_FREEZE`
- Branch: `research/raj-arora-external-seeded-proxy-v1`
- Runtime authority: `NONE`
- Broker actions permitted: `false`
- Edge certified: `false`
- Validation accessed: `false`
- Holdout accessed: `false`
- Development cells declared and evaluated: `54`
- Frozen chronological split: `295 development / 98 validation / 100 holdout`
- Frozen development round-trip cost: `2 bps`
- Frozen minimum development trades: `50`

## Replay-source reconciliation

A previously supplied archive, `kite_candidate_replay(2).zip`, was recovered from the user's file library and inspected independently.

Observed NIFTY underlying replay inventory:

- NIFTY session parquet files: `493`
- date range: `2024-07-09` through `2026-07-08`
- total NIFTY rows across the 493 session files: `36,849`
- ordinary sessions: `491 x 75 bars`
- special sessions: `2024-11-01` and `2025-10-21`, `12 bars` each
- observed `synthetic=true` rows: `0`
- observed `fallback=true` rows: `0`
- observed `mock=true` rows: `0`
- archive SHA-256 observed in the analysis environment: `a7d302f714e1a91a81e71ea51500243967a8fd0be26fb71188552112cef440f1`

The row count and session count reconcile exactly to the frozen NIFTY corpus characteristics. However, this run does **not** claim exact-byte equality to the canonical CSV at SHA-256 `6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8`, because canonical CSV serialization/provenance bytes were not reproduced in this environment. Therefore the results below are classified as `REPLAY_SOURCE_RECONCILED_DEVELOPMENT_EVIDENCE`, not exact-byte canonical certification evidence.

## Frozen V1 family results

### A. Opening-range breakout -> retest -> continuation

Verdict: `REJECTED_IN_DEVELOPMENT`.

The family did not produce an admissible positive development candidate. Its best observed cell was still negative and below the minimum-trade gate:

- opening range: `15 minutes` (`3 x 5m bars`)
- breakout buffer: `0 bps`
- forward horizon: `30 minutes` (`6 bars`)
- trades: `35`
- mean net return: `-1.4735 bps/trade`
- win rate: `51.43%`

This is consistent with adverse prior evidence against simple ORB continuation forms.

### B. Opening-range failed breakout -> reversal

Verdict: `DEVELOPMENT_NOMINATION_FOUND`.

Best frozen cell:

- opening range: `10 minutes` (`2 x 5m bars`)
- breakout close buffer: `5 bps` beyond the opening-range boundary
- failure condition: a later completed close returns inside the opening range within `2 bars`
- direction: opposite the failed breakout
- entry: next completed 5m-bar close after failure confirmation
- horizon: `30 minutes` (`6 bars`)
- trades: `57`
- mean net return after frozen 2 bps cost: `+3.809970731 bps/trade`
- win rate: `63.1579%`
- total net return: `+217.1683 bps`

Same signal at a 15-minute forward horizon:

- trades: `57`
- mean net return: `+0.83494 bps/trade`
- win rate: `50.877%`
- total net return: `+47.591 bps`

The apparent edge is therefore mainly a slower post-failure move rather than an immediate one-bar reversal.

### C. Opening drive -> orderly pullback -> resumption

Verdict: `REJECTED_IN_DEVELOPMENT_INSUFFICIENT_SUPPORT`.

A few cells had positive means but were far below the frozen 50-trade minimum. Examples:

- 15-minute drive >=25 bps, 30-minute horizon: `6 trades`, `+3.316 bps/trade`
- 15-minute drive >=15 bps, 30-minute horizon: `14 trades`, `+2.938 bps/trade`

These are too sparse to nominate.

## Predeclared robustness diagnostics on the failed-breakout nomination

All diagnostics below use development sessions only. Validation and holdout remain untouched.

### Cost stress

| Round-trip cost | Mean net bps/trade | Win rate |
| ---: | ---: | ---: |
| 0 bps | +5.80997 | 64.91% |
| 2 bps | +3.80997 | 63.16% |
| 5 bps | +0.80997 | 49.12% |
| 10 bps | -4.19003 | 31.58% |

Verdict: `FRICTION_FRAGILE`. The signal stays slightly positive at 5 bps but fails at 10 bps.

### Entry-delay stress

| Entry timing | Trades | Mean net bps/trade |
| --- | ---: | ---: |
| Frozen next-bar entry | 57 | +3.80997 |
| One additional 5m bar late | 56 | +1.97438 |
| Two additional 5m bars late | 56 or fewer depending on session end | -0.79203 |

Verdict: `TIMING_SENSITIVE`.

### Parameter-neighborhood stability

At the same 30-minute horizon:

| Opening bars | Breakout buffer | Trades | Mean net bps/trade |
| ---: | ---: | ---: | ---: |
| 2 | 0 bps | 116 | -2.29392 |
| 2 | 5 bps | 57 | **+3.80997** |
| 3 | 0 bps | 109 | -3.52496 |
| 3 | 5 bps | 44 | -1.61812 |
| 6 | 0 bps | 113 | -4.36048 |
| 6 | 5 bps | 47 | -8.05845 |

Verdict: `NEIGHBORHOOD_STABILITY_FAIL`. The positive result is an isolated parameter island rather than a broad plateau.

### Chronological stability inside development

Chronological thirds:

- `2024-07-09` to `2024-11-28`: 19 trades, `+0.13927 bps/trade`, 42.1% wins
- `2024-11-29` to `2025-04-24`: 17 trades, `+4.10852 bps/trade`, 76.5% wins
- `2025-04-25` to `2025-09-15`: 21 trades, `+6.88940 bps/trade`, 71.4% wins

By development calendar year:

- 2024: 22 trades, `+0.49893 bps/trade`, 50.0% wins
- 2025 through 2025-09-15: 35 trades, `+5.89119 bps/trade`, 71.4% wins

Verdict: `TEMPORALLY_UNSTABLE_OR_REGIME_DEPENDENT`. Most apparent edge arrives in later development sessions.

### Direction asymmetry — diagnostic only

This was observed after the frozen V1 development result and is **not** an authorized V1 selection rule:

- upward reversal after failed downside breakout: 33 trades, `+6.62084 bps/trade`, 69.70% wins
- downward reversal after failed upside breakout: 24 trades, `-0.05497 bps/trade`, 54.17% wins

This asymmetry may motivate a separately frozen future generation, but selecting the profitable side inside V1 would be post-hoc threshold/rule laundering and is forbidden.

### Randomized-direction null

Deterministic 20,000-draw development null:

- observed mean net: `+3.80997 bps`
- null mean: approximately `-1.99994 bps`
- null 95th percentile: `+1.67320 bps`
- one-sided empirical p-value: approximately `0.00345`

The observed direction mapping is unlikely to be explained by random direction labels alone.

### Session-pairing null

Deterministic 5,000-draw development null:

- observed mean net: `+3.80997 bps`
- null mean: `-1.95647 bps`
- null 95th percentile: `+2.31786 bps`
- one-sided empirical p-value: approximately `0.0144`

The signal is unlikely to be explained solely by arbitrary signal/session pairing.

### Profit concentration

- maximum trade: `+55.13 bps`
- minimum trade: `-29.32 bps`
- median trade: `+2.162 bps`
- largest winning trade contributes approximately `25.4%` of total development net return
- top five winning trades contribute approximately `90.2%` of total development net return

Verdict: `CONCENTRATION_RISK_HIGH`.

## Controlled verdict

```text
EXACT_VIDEO_STRATEGY_CLAIMED=false
DEVELOPMENT_SURVIVOR=true
SURVIVING_PROXY=OPENING_RANGE_FAILED_BREAKOUT_REVERSAL
VALIDATION_ACCESSED=false
HOLDOUT_ACCESSED=false
PARAMETER_NEIGHBORHOOD_STABILITY=FAIL
COST_10_BPS_STRESS=FAIL
ENTRY_DELAY_STABILITY=WEAK
TEMPORAL_STABILITY=WEAK
PROFIT_CONCENTRATION=HIGH
CERTIFIED_STRATEGY=false
STRUCTURAL_EDGE_CERTIFIED=false
TRADEBOT_INTEGRATION_ALLOWED=false
RUNTIME_AUTHORITY=NONE
NEXT_ACTION=DO_NOT_SPEND_VALIDATION_ON_V1
```

The correct interpretation is that V1 found an interesting **failed-opening-breakout reversal hypothesis**, not a certified strategy. Its randomized controls are encouraging, but the isolated parameter island, friction sensitivity, temporal instability, directional asymmetry, and concentration are strong enough to stop V1 before validation.

A future V2 is permissible only as a new, explicitly frozen multiple-testing family justified by the V1 failure decomposition. It must not reuse validation or holdout to choose its thresholds, and it must not silently convert the post-hoc upward-reversal observation into a certified rule.

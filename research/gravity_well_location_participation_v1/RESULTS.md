# Gravity-Well Location + Participation Research V1 — Results

## Final verdict

```text
DATA_BLOCKED_MISSING_VOLUME_CONSTITUENTS_AND_REAL_OPTIONS
NO_PRICE_ONLY_VALIDATION_SURVIVOR
```

The uploaded archive materially improved the evidence base, but it does **not** contain the data required to test the full claimed mechanism. A bounded price-only underlying diagnostic was completed; it failed validation. The 99-session holdout remained sealed.

This does **not** prove that the complete volume + participation + option mechanism has no edge. It proves that the available archive cannot test that mechanism, and that the price-only substitute is not worth integrating or tuning.

## Source audit

- Source ZIP SHA-256: `f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d`
- Parquet files: **1,509**; parsed successfully: **1,509**; failures: **0**
- Underlying files: **1,479**; option files: **30**
- Total rows: **120,282**; underlying rows: **110,547**; option rows: **9,735**
- NIFTY: **493 sessions**, **36,849 five-minute rows**, from `2024-07-09T09:15:00+05:30` through `2026-07-08T15:25:00+05:30`
- Underlying nonzero-volume rows: **0**
- Underlying authority flags: synthetic **0**, fallback **0**, mock **0**
- Instruments present: NIFTY, BANKNIFTY and SENSEX only. No NIFTY constituent bars were found.
- All 30 option paths are explicitly named `*_OPT_MOCK_ltp.parquet`. Their schema contains only `timestamp, open, high, low, close, volume`; expiry, strike, option type and contract identity are absent.

### Hard consequence

The canonical Gravity-Well centre cannot be calculated because every underlying volume value is zero. Constituent participation cannot be calculated because constituents are absent. Option outcomes cannot be reconstructed because the only option files are mock-named and lack contract identity. Any claim of option edge from this ZIP would be fabricated.

## Frozen diagnostic lane

Before outcome evaluation, the fallback diagnostic was frozen as an **EMA-centre price-only proxy**, not a Gravity-Well replication:

- NIFTY five-minute completed bars; EMA 20; Wilder ATR 14; outer band 1.5 ATR; extreme band 2.0 ATR.
- Completed 15-minute and 30-minute rolling levels plus previous-session high/low.
- Next-bar entry only; no cross-session outcome; primary horizon six bars/30 minutes.
- Chronological split: 295 development sessions / 99 validation sessions / 99 sealed holdout sessions.
- Zero-cost diagnostic, 2 bps primary cost and 5 bps severe cost.
- Centre-length neighbours: 14 and 30; no profitability grid search.
- Direction/time-bucket matched random baseline with 2,000 replications.

## Primary price-only results

| Family | Dev trades | Validation trades / sessions | Gross exp. | Net 2 bps exp. | Net 5 bps exp. | PF at 2 bps | 95% session CI | After top 5 | After top 2 sessions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Escape acceptance | 308 | 134 / 79 | -1.49 | -3.49 | -6.49 | 0.39 | [-5.23, -1.90] | -4.29 | -3.93 |
| Failed escape | 39 | 7 / 7 | 2.77 | 0.77 | -2.23 | 1.38 | [-3.29, 4.60] | -6.48 | -1.75 |
| Cluster-break acceptance | 106 | 20 / 20 | -1.96 | -3.96 | -6.96 | 0.46 | [-10.74, 2.24] | -8.98 | -6.30 |

### Interpretation

**Escape acceptance failed clearly.** Validation expectancy was −3.49 bps after a minimal 2 bps cost, profit factor was 0.39, and the entire session-bootstrap interval was below zero. It also performed worse than its matched random baseline; its actual expectancy ranked at only the 7.3rd percentile of the random distribution.

**Cluster-break acceptance failed and lacked support.** It produced only 20 validation trades and lost before and after costs. Removing the largest winners made it materially worse.

**Failed escape is a false lead, not a survivor.** Its validation mean was +0.77 bps after 2 bps, but that came from only 7 trades across 7 sessions. The confidence interval crossed zero widely; expectancy became −6.48 bps after removing the five largest winners and −1.75 bps after removing the top two sessions. Under 5 bps cost it was already −2.23 bps. It failed the predeclared support, concentration, severe-cost and neighbour-robustness gates.

## Price-only baselines

| Baseline | Validation trades | Net 2 bps expectancy | Profit factor | 95% session CI |
|---|---:|---:|---:|---:|
| EMA cross | 322 | -2.07 | 0.66 | [-2.58, 0.59] |
| ATR displacement continuation | 216 | -1.81 | 0.67 | [-3.19, 0.72] |
| Direct outer-band fade | 216 | -2.19 | 0.62 | [-4.72, -0.81] |
| HTF cluster break | 84 | -2.23 | 0.62 | [-5.35, 0.15] |

All simple baselines were negative. This shows that neither continuation, fading, EMA crossing nor clustered-level breaking has raw 30-minute directional expectancy in this corpus under the frozen event rules.

## Neighbour robustness

| Centre length | Escape acceptance | Failed escape | Cluster break |
|---:|---:|---:|---:|
| 14 | -2.10 | -4.15 | -3.70 |
| 20 | -3.49 | 0.77 | -3.96 |
| 30 | -3.00 | -4.14 | -8.08 |

The isolated failed-escape gain at length 20 disappears at both predeclared neighbours. That is exactly the pattern expected from sparse winner concentration, not stable mechanism evidence.

## Integrity and reproducibility

- Focused validation checks: **10 passed / 10**.
- Tests cover future-HTF mutation, next-bar entry, holdout isolation, authority flags, zero volume, mock option exclusion and contract-identity absence.
- Event ledger deterministic SHA-256: `37a21a64f74f632f1c31ecc3bf14cefd4e2d2eeeb8c732c23e3e2c4c26d8ae4d`
- Certification deterministic SHA-256: `5c830f4cc18b1a3c57593f89b65938cf91a822063e082caa065f4adffc961846`
- A complete rerun produced byte-identical event-ledger and certification hashes.
- No holdout performance was calculated because no validation survivor existed.

## Decision

1. **Do not integrate any of these price-only variants into TradeBot.**
2. **Do not tune thresholds against this validation set.** That would be post-selection.
3. **Do not use the `OPT_MOCK` files for P&L or option certification.** Their names and missing identity make them non-authoritative.
4. The complete Gravity-Well hypothesis remains data-blocked, not disproved. It may be resumed only with:
   - nonzero trustworthy volume or a separately justified frozen centre definition;
   - timestamp-aligned NIFTY constituent bars;
   - real expired-option OHLC plus expiry, strike, CE/PE and immutable contract identity;
   - the preserved Market Event Graph corpus for an incremental comparison.

Targeted Drive searches did not locate `causal-market-state-v1-evidence-v3`, `canonical_option_intents`, or `option_trade_ledger`. The uploaded ZIP therefore remains the best verified corpus available in this session.

## Truthful campaign status

```text
IMPLEMENTATION_COMPLETE
SOURCE_ARCHIVE_FULLY_AUDITED
PRICE_ONLY_DIAGNOSTIC_COMPLETE
NO_PRICE_ONLY_VALIDATION_SURVIVOR
HOLDOUT_SEALED
FULL_GRAVITY_WELL_MECHANISM_DATA_BLOCKED
NO_STRATEGY_INTEGRATION
NO_OPTION_EDGE_CLAIM
```

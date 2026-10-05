# NIFTY 45-DTE VRP Research Package V1

## Status

`DATA_GATED / NOT_CERTIFIED / RESEARCH_ONLY`

This package converts the public 45-DTE NIFTY strategy idea into two separately governed candidates:

1. `NIFTY_45DTE_VRP_V1` — a direct short-volatility research reproduction.
2. `NIFTY_45DTE_VRP_TRANSLATOR_BUYONLY_V1` — a BUY-only context gate that never creates or reverses a trade.

Neither candidate has paper, live, broker-write, or order authority.

## Source exactness

Source video: `https://youtu.be/z9nviVN6pa8`

Title: **I Backtested the Famous 45 DTE Strategy on NIFTY | The Long & The Short Ep. 48**

The accessible video page did not expose the exact transcript/rule text. Therefore the direct candidate is explicitly marked `PARTIALLY_RECOVERED`: the 45-DTE / approximately 16-delta / around-21-DTE management family comes from the canonical public strategy family, while the 50% profit target is treated as a family convention rather than claimed as a verbatim rule from this video.

Do not change `source_exactness` to exact unless the actual source transcript/rules are recovered and hashed.

## Why the existing synthetic replay cannot be used

`core/historical_option_chain_realish.py` explicitly describes itself as synthetic. It fabricates IV, smile/skew, spreads, OI, volume, Greeks and a nearby inferred expiry. It is useful for software-path testing but cannot establish whether a 45-DTE NIFTY volatility premium existed historically.

The direct strategy therefore rejects sources marked synthetic/realish/simulated/mock/fixture.

## Candidate 1 — direct 45-DTE short-vol reproduction

Frozen primary:

- underlying: NIFTY
- expiry: monthly family
- entry: first eligible 42–48 calendar-DTE session, approximately 15:00 IST
- legs: short CE and short PE nearest absolute delta 0.16, tolerance 0.03
- entry execution: sell at contemporaneous bid
- primary exit: first 50% initial-credit capture, otherwise approximately 21 DTE
- exit execution: buy to close at contemporaneous ask
- one position per expiry
- no optimization of the primary specification

`audit_data.py` first proves whether a supplied historical dataset can support the test. `evaluate_short_vol.py` refuses synthetic sources and performs only descriptive research evaluation.

### Minimum direct-strategy data

`timestamp, symbol, expiry, strike, type, bid, ask, delta`

Preferred additional fields:

`ltp, iv, underlying_spot, volume, oi`

A final cost claim still requires explicit statutory/brokerage/tax modelling in addition to executable-side bid/ask treatment.

## Candidate 2 — BUY-only VRP translator

The translator asks a different question: does the medium-dated volatility state improve an already-frozen directional option-buying strategy?

`build_vrp_state.py` computes:

- near-ATM IV for eligible 35–55 DTE expiries from real option observations,
- IV45 by linear DTE interpolation when 45 DTE is bracketed, otherwise nearest expiry only within ±5 days,
- RV20 from the **prior 20 completed** NIFTY close-to-close returns,
- `VRP = IV45^2 - RV20^2`,
- a current VRP z-score against **prior state observations only**, minimum 60 prior observations.

Primary preregistered gate:

`admit frozen BUY-only baseline trade iff latest available vrp_zscore <= 0`

No threshold optimization is allowed for the primary result.

### Critical lookahead rule

The state is timestamped at the real option snapshot near 15:00 IST. `evaluate_buyonly_gate.py` uses a backward as-of join with:

`state_timestamp <= trade_entry_timestamp`

Therefore a 09:20 trade on Monday cannot see Monday's 15:00 volatility state; it uses the most recent prior state, normally Friday's. A 15:10 Monday trade may use Monday's 15:00 state.

## Tests

- synthetic/`realish` option source rejection
- minimum real-quote capability audit
- 50% profit-target path
- losing 21-DTE time-exit path
- RV20 excludes the current session close
- morning trades cannot see the same day's 15:00 state
- missing state history is not silently counted as a rejected trade

The first four tests were exercised in an isolated local fixture before commit. The complete committed suite must pass repository CI before this branch can be considered implementation-valid.

## Required research path

This candidate does not bypass the repository's existing strategy deep-dive or fail-closed MROS certification.

Before any positive edge claim, the evidence must separately cover:

1. source/data provenance and immutable hashes
2. lookahead/leakage audit
3. signal/trade frequency and coverage
4. regime isolation
5. realistic cost evidence
6. MFE/MAE and tail-loss concentration
7. management sensitivity
8. execution/proxy validation where relevant
9. friction stress through 3x
10. temporal stability, including 2024 / 2025 / 2026 separation
11. historical OOS
12. prospective observation
13. independent verification

The repository MROS certification layer additionally requires verified `prospective`, `historical_oos`, `cost_evidence`, `robustness`, and `independent_verification` artifacts bound to an exact candidate SHA.

## Current blocker

No positive/negative strategy conclusion is claimed yet. The exact outcome evaluation is blocked until a real historical NIFTY option dataset is supplied that preserves enough multi-expiry history to follow the same contracts from approximately 45 DTE toward 21 DTE and contains the execution fields required by the data contract.

Public OHLC/OI expired-option archives can be useful for exploratory diagnostics, but OHLC without historical bid/ask cannot satisfy the final execution-cost evidence requirement.

## Example commands

Data capability audit:

```bash
python research/nifty_45dte_vrp_v1/audit_data.py OPTIONS.parquet \
  --output runtime/research/nifty_45dte_vrp_v1/data_audit.json \
  --expected-sha256 <sha256>
```

Direct primary descriptive replay:

```bash
python research/nifty_45dte_vrp_v1/evaluate_short_vol.py OPTIONS.parquet \
  --output-dir runtime/research/nifty_45dte_vrp_v1/primary \
  --expected-sha256 <sha256>
```

Build BUY-only VRP states:

```bash
python research/nifty_45dte_vrp_v1/build_vrp_state.py OPTIONS_WITH_IV.parquet NIFTY.parquet \
  --output runtime/research/nifty_45dte_vrp_v1/vrp_states.csv \
  --summary runtime/research/nifty_45dte_vrp_v1/vrp_state_summary.json \
  --expected-options-sha256 <sha256> \
  --expected-underlying-sha256 <sha256>
```

Evaluate on a frozen BUY-only ledger:

```bash
python research/nifty_45dte_vrp_v1/evaluate_buyonly_gate.py BASELINE_LEDGER.csv VRP_STATES.csv \
  --output-dir runtime/research/nifty_45dte_vrp_v1/buyonly_gate \
  --baseline-candidate-sha <40-char-git-sha> \
  --expected-baseline-sha256 <sha256> \
  --expected-states-sha256 <sha256> \
  --pnl-column <frozen-net-outcome-column>
```

## Governance

- research only
- no broker API calls
- no broker writes
- no orders
- no paper authorization
- no live authorization
- no holdout access in this package
- no structural-edge certification from descriptive output

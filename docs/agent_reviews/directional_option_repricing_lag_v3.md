# Directional Option Repricing-Lag V3 — Agent Review Evidence

- timestamp: `2026-07-22T11:30:00Z`
- branch: `research/directional-option-repricing-lag-v3`
- base: `research/structural-edge-prove-or-kill-v1`
- hypothesis: `DORL_V3`
- execution side: `BUY_ONLY`
- initial authoritative verdict: `BLOCKED_NEED_OPTION_MICROSTRUCTURE_DATA`

## Agent Work Contract

Preregister the fifth and final hypothesis in the bounded structural-edge campaign. Implement a deterministic, buy-only NIFTY CE/PE repricing-lag signal oracle, Black-76 price/Greek reconstruction, strict executable-quote validation, and a read-only data-readiness audit. Do not implement production trading or claim an edge.

## Scope Guard

Allowed paths are limited to the DORL research signal, math and readiness modules, frozen specification, campaign registry, focused runner, focused tests, one workflow, package exports, and this review document. No broker, order, feed, risk, execution, ranking, dashboard, credential, live configuration, or production strategy file is modified.

## Grill Me Review

The strategy is rejected before research whenever futures ticks, option ticks, or the same-day instrument master are absent. It does not substitute NIFTY candles for futures order flow, raw option LTP for executable bid/ask, or midpoint fills for buy-at-ask and sell-at-bid semantics. A positive development candidate is impossible from the readiness audit alone.

## Hermes Review

The signal uses only contemporaneous or backward-looking fields. The candidate direction is determined from a completed three-minute futures impulse; CE is eligible only for bullish impulses and PE only for bearish impulses. Reference IV joins must be backward-as-of. Future realized PnL fields are excluded from the signal fingerprint and mutation-tested.

## GSD Review

The frozen campaign now contains exactly five hypotheses and exactly forty total variants. DORL-V3 consumes the remaining four-variant budget. The specification freezes DTE, 0.55–0.70 absolute-delta band, time window, buy-only execution, quote age, OFI, option-flow, book-imbalance, IV-shock, cost-buffer, latency, holding-time, and negative-control contracts before any outcome screen. The signal oracle rejects contracts outside the frozen delta band.

## QA / Safety Review

The focused suite proves Black-76 inversion, finite Greeks, bullish CE and bearish PE symmetry, frozen delta-band rejection, stale/wrong-side rejection, already-repriced IV rejection, future-mutation isolation, complete-data readiness, missing-futures rejection, candidate-free blocked evidence, and invalid-quote rejection. All artifacts are read-only, contain no order action, call no broker, and grant no live permission.

## Acceptance Proof

Required evidence:

```text
python -m py_compile research/structural_edge_campaign/option_repricing_lag.py research/structural_edge_campaign/option_repricing_lag_math.py research/structural_edge_campaign/option_repricing_lag_data.py scripts/run_directional_option_repricing_lag_development.py tests/test_directional_option_repricing_lag_v3.py
PYTHONPATH=. python -m pytest -q tests/test_directional_option_repricing_lag_v3.py tests/test_structural_edge_campaign.py
```

The GitHub workflow must produce two byte-identical evidence files with valid SHA-256 sidecars and the exact verdict `BLOCKED_NEED_OPTION_MICROSTRUCTURE_DATA` while no qualifying dataset is supplied.

## Runtime Proof Required After Merge

Before development screening, provide immutable, byte-hashed datasets with at least thirty overlapping sessions containing same-timestamp NIFTY futures ticks and option ticks with bid, ask, depth, volume, instrument identity, and at least two expiries. Then implement causal signal construction, next-eligible-quote entry, strict `OptionBacktestEngine` replay, chronological option WFA, and the campaign's existing fresh-confirmation and holdout gates.

## What This PR Does Not Prove

This PR does not prove structural edge, profitability, option PnL, execution quality, paper readiness, live readiness, or capital suitability. It does not produce a frozen candidate. Workflow success proves only that the hypothesis is preregistered, the math and safety contracts behave deterministically, and missing data is reported honestly.

## Human Approval

Human approval is required before adding a new microstructure corpus, running any fresh-confirmation cohort, unlocking the global holdout, implementing paper/shadow behavior, or changing production TradeBot files. The PR must remain draft and must not auto-merge.

mode: PRODUCTION_CALCULATION_LIBRARY_WITHOUT_LIVE_WIRING
candidate_id: option_analytics_v1
base_sha: 596fff09859afeca292bc3e3e31d4a55db1fd8c6
branch: feature/production-option-analytics-v1
read_only_runtime: true
broker_api_called: false
is_order_action: false
strategy_signal_changed: false
candidate_ranking_changed: false
risk_gate_changed: false

# Option Analytics V1

## Objective

Add production-quality, dependency-light European-option analytics without changing live execution, candidate selection, strategy signals, ranking, or risk gates.

## Implemented

- Black–Scholes–Merton pricing with continuous dividend yield.
- Black–76 pricing with an explicit forward/futures input.
- Typed immutable inputs/results and fail-closed calculation statuses.
- Exact timezone-aware time to expiry using elapsed seconds and ACT/365F.
- Analytic delta, gamma, theta, vega, and rho with explicit units.
- Deterministic bracketed implied-volatility inversion with model bounds.
- Strict quote provenance, freshness, crossed-market, and locked-market handling.
- Same-expiry, same-option-type IV-surface diagnostics using log-forward moneyness.
- Immutable candidate enrichment that does not rewrite strategy fields.
- Discrete pathwise Greek P&L attribution with an explicit residual and approximation limitations.
- A deterministic 96-case audit grid with 48 put-call-parity checks.

## Fail-closed behaviour

Invalid/non-finite inputs return typed failures rather than numeric zeroes. IV prices outside model bounds return `OUTSIDE_NO_ARBITRAGE_BOUNDS`. Unbracketed and maximum-iteration cases return no implied volatility. Stale midpoint requests do not silently fall back to last price.

## Mathematical evidence

Local isolated verification on Python 3.13.5:

- Focused tests: `68 passed`.
- Audit grid: `96` pricing/Greeks/IV cases.
- Put-call parity: `48` cases.
- Identifiable IV round trips: `48` cases.
- Numerically lower-bound/zero-time-value cases: `48` explicitly classified, not falsely treated as recoverable IV.
- Audit failures: `0`.
- Audit semantic SHA-256: `20d762b4bd11cda982c0ef61aa9cdbab585eb8cb3c9a0b2f31e36f07540773b1`.

## Legacy defects addressed by the new API

The existing `core/greeks.py` remains untouched for compatibility. The new API avoids its ambiguous zero-on-invalid contract, unbracketed Newton solver, hidden rate dependency, ambiguous Greek units, missing dividend/forward conventions, and put-theta sign issue. It also requires exact timestamps rather than integer calendar-day expiry proxies.

## Safety and integration boundary

This PR deliberately does not wire the library into `core/option_chain.py`, broker calls, order routing, dashboards, ranking, strategy selection, or risk gates. Production wiring requires a separate compatibility and replay-validation PR because replacing current calculations inside a live option-chain path without repository-wide replay evidence would be unsafe.

## Limitations

- Models are European-option analytical models, not market truth.
- Surface residuals are diagnostics, not trade recommendations or arbitrage claims.
- P&L attribution is a discrete local approximation; higher-order and cross-Greek effects remain in the residual.
- Lower-bound options can have volatility that is numerically non-identifiable from price.
- No live, broker, holdout, or real/replay P&L data was consumed.

## Publication status

The code is suitable for review as a production calculation library, but live activation is not authorized by this PR.

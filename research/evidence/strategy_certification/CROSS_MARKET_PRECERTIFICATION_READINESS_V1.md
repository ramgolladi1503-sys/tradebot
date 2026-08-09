# Cross-Market Precertification Readiness V1

Status: `ONE_CANDIDATE_REMAINS`

Research only. Runtime authority: `NONE`. Broker actions: `FALSE`. Edge claimed: `FALSE`.

## Frozen implementation

- Source commit: `561041b2e11f03283ebca3fd5eb70e6ef6fc1d6d`
- Strategy generation freeze: `REGISTERED_ALPHA_FREEZE_MANIFEST_V1`

## Synchronized dataset

The deterministic repository builder `scripts/research/hypothesis_factory/build_cross_market_matrix.py` reproduces the declared synchronized dataset from the three frozen canonical underlying CSVs using `EXACT_INTERSECTION` and `CURRENT_OR_PRIOR_ONLY` feature timing.

Local native reproduction evidence supplied by the operator:

- rows: `36849`
- sessions: `493`
- first session: `2024-07-09`
- last session: `2026-07-08`
- BANKNIFTY input SHA-256: `ff5474cb0662e9f4bc0642dab6e00a2648cfe2da16161ab174c9324c0f22ef50`
- NIFTY input SHA-256: `6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8`
- SENSEX input SHA-256: `ad2cf219cd5054a0cac8771da504f3b9215fa6220341b92fd5ac4563e2d342a7`
- synchronized output SHA-256: `66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32`
- rebuilt SHA matches the previously declared frozen hash exactly.

## Strategy determinations

### `pairs_arbitrage`

Readiness: `READY_FOR_DEDICATED_EDGE_CERTIFICATION_HARNESS`

Reasoning:

- The frozen callable consumes two current prices plus aligned historical price legs.
- Hedge ratio and intercept are estimated internally by the frozen Kalman filter path.
- Spread truth, z-score, ADF stationarity truth and OU half-life are calculated from aligned price history.
- Leg freshness can be represented truthfully by exact-timestamp synchronized rows (`age = 0`) because the synchronized dataset is an exact intersection, provided the harness enforces this directly and never substitutes unmatched rows.
- Cross-asset health may be asserted only as a deterministic data-integrity predicate derived from the already verified synchronized artifact (hash verified, same timestamp, both leg prices finite/positive). It must not be fabricated as a market-quality opinion.
- The signal output is `BUY_SPREAD` / `SELL_SPREAD`, so research returns can be evaluated on the two underlying legs without synthesizing option premiums.

This is readiness only, not edge certification.

### `volatility_trend`

Readiness: `INSUFFICIENT_EVIDENCE`

Reasoning:

- Cross-asset confirmation can in principle be reconstructed from synchronized underlying series.
- ATR can in principle be derived causally from underlying OHLC.
- However the frozen implementation converts underlying LTP into an option strike and manufactures `entry_price` using `ltp * 0.004` clipped to configured premium limits, then derives stop and target from that synthetic premium.
- No historical option premium path in the verified corpus supports those execution economics.
- Profitability or structural-edge certification would therefore require synthetic option outcomes and is prohibited.

## Next allowed action

Build a dedicated research-only certification harness for frozen `pairs_arbitrage` only. The harness must preserve the frozen strategy implementation and evaluate exact causal two-leg executions over the synchronized dataset with chronological OOS / walk-forward testing, parameter-neighborhood robustness, transaction-cost and slippage stress for both legs, negative controls, regime/time stability, sufficient signal count, and explicit multiple-testing handling where applicable.

The harness must not modify strategy thresholds based on certification or holdout results. Any changed strategy logic or thresholds create a new passport identity.

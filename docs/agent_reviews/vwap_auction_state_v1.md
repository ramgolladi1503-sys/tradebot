# VWAP Auction State V1 — Agent Review Evidence

mode: RESEARCH_ONLY
candidate_id: VWAP_AUCTION_STATE_V1
decision: FORMULA_IMPLEMENTED_VALIDATION_PENDING
reason: Implement a causal futures-volume auction-state formula and executable long-option research boundary without runtime wiring.
timestamp: 2026-08-24T21:04:00+05:30
is_order_action: false
broker_api_called: false
read_only: true
allowed_for_runtime_wiring: false
allowed_for_live_execution: false

## Agent Work Contract

Build one standalone research implementation for three VWAP/auction mechanisms: failed discovery returning to value, accepted discovery pullback continuation, and balance-extreme mean reversion. Signal formation must use authoritative NIFTY futures traded volume. Option execution must remain BUY ONLY and causal. Do not modify broker/order/risk-runtime/live-feed/credential/deployment paths or production strategy registration.

## Scope Guard

Allowed paths are `research/vwap_auction_state_v1/**`, focused tests, this review document, and focused CI. Production `strategies/**`, candidate-generation wiring, broker adapters, live launch, execution authority, risk-engine behavior, and credentials remain out of scope.

## Grill Me Review

1. Why not NIFTY spot VWAP? NIFTY spot has no authoritative traded volume. This candidate rejects zero-volume and unit-weight VWAP and uses active NIFTY futures as the volume-bearing signal authority.
2. Can a completed signal bar fill itself? No. Contract selection uses only information timestamped at or before the signal and entry requires the first eligible option ask strictly after the signal timestamp.
3. Can futures price silently determine ATM option strike? No. The economic evaluator requires a contemporaneous NIFTY spot/index reference for option moneyness and fails closed if it is missing.
4. Can the strategy sell options? No. The only directions are `BUY_CALL` and `BUY_PUT`.
5. Is a mid-price or assumed-tight spread used? No. Entry uses executable ask, exit uses executable bid, and stale/wide quotes are rejected.
6. Can a same-minute stop/target ambiguity flatter results? No. V1 resolves simultaneous 1-minute stop and target touches adversely as a stop.
7. Were thresholds selected by maximizing historical PnL? No. V1 freezes one base formula plus nine small one-factor robustness variants and requires a stable plateau rather than the best cell.
8. Can holdout results be used to rewrite V1? No. A post-outcome formula change requires a separately frozen version.
9. Can this work grant LIVE authority? No. There is no runtime wiring and every artifact remains explicitly ineligible for live execution.

## Hermes Review

The architecture is deliberately two-stage. NIFTY futures carry the volume-bearing auction state; contemporaneous NIFTY spot/index truth supplies option moneyness; NIFTY option bid/ask quotes express the trade. Option-premium VWAP is not used as market-state authority. The implementation does not reuse the permissive legacy VWAP helper because historical repository evidence already shows zero-volume assumptions, signal-spam risk, and negative proxy results in those older paths.

## GSD Review

Implemented layers:

- causal session VWAP and weighted dispersion from authoritative futures volume;
- normalized distance, efficiency ratio, and VWAP-slope regime state;
- explicit `BALANCE`, `UP_DISCOVERY`, `DOWN_DISCOVERY`, `TRANSITION`, and warmup states;
- three separate frozen mechanisms with structural stops/targets and minimum 1.5R geometry;
- failed-auction priority over continuation;
- buy-only CE/PE translation;
- causal spot reference for option strike/moneyness;
- DTE, spread, quote freshness, volume and OI gates;
- next-quote ask entry and bid exit;
- conservative one-minute stop/target ordering;
- non-overlapping trades, 15-minute cooldown and three-signal session cap;
- 30-minute maximum hold, 14:45 last entry and 15:15 forced exit;
- total-premium sizing capped at 5% of account equity;
- small predeclared robustness lattice rather than Cartesian optimization.

## QA / Safety Review

Standalone local validation before publication:

```text
python -m py_compile research/vwap_auction_state_v1/model.py research/vwap_auction_state_v1/backtest.py -> PASS
python -m pytest -q tests/research/test_vwap_auction_state_v1.py tests/research/test_vwap_auction_state_backtest_v1.py -> 12 passed
```

The tests cover authoritative-volume rejection, weighted VWAP, discovery classification, all three mechanism directions, structural R:R, buy-only option selection, next-quote ask entry, 0DTE separation, 5% premium-risk sizing, robustness-lattice uniqueness, adverse same-bar path handling, and option-point accounting.

## Kernel / Certification Boundary

The repository's existing governed research lifecycle remains authoritative. Economic promotion requires hash-pinned PASS evidence for:

1. causal timestamps;
2. true next-bar execution;
3. transaction costs and slippage;
4. deterministic replay;
5. negative controls;
6. walk-forward analysis;
7. untouched holdout;
8. independent oracle;
9. artifact integrity.

V1 additionally requires futures-volume provenance, causal spot reference, executable option bid/ask truth, 0DTE stratification, formula-family multiple-testing correction, parameter-neighborhood stability, cost sensitivity, and era/month/regime concentration checks.

## Acceptance Proof

Engineering acceptance requires exact-head compilation, the focused invariant tests, repository CI/agent-review checks, and a changed-path audit showing no runtime or execution-authority modification. Passing those checks proves only that the frozen research implementation is internally consistent and safe to evaluate; it does not prove an economic edge.

## Runtime Proof Required After Merge

No live runtime proof is authorized or required. Before any paper-eligibility discussion, run the frozen V1 formula through the governed historical pipeline against the kernel-authoritative local corpus on the TradeBot data volume, preserving its existing DEV/OOS/HOLDOUT boundaries and using real futures volume plus executable option bid/ask data. The one-day zero-volume spot proxy is not an acceptable substitute.

## What This PR Does Not Prove

This work does not prove positive expectancy, profitability, structural edge, achievable future fills, paper eligibility, or live readiness. It has not opened the untouched holdout. It does not treat spot-scaled option PnL as executable option truth, and it does not claim that the default formula is economically correct until the governed historical gates are actually run.

## Human Approval

No merge into live authority, runtime wiring, paper promotion, LIVE promotion, or capital allocation is authorized by this work. Any later promotion requires separate evidence and explicit human approval under the existing TradeBot governance boundary.

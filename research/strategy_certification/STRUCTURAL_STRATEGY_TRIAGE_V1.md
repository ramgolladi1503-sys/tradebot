# Structural Strategy Triage V1

Source structural audit commit: `cd874d1ce50514805de71d61ed64e4de5baf7f9e`

Purpose: classify static structural-audit findings before any strategy repair. This document does not evaluate profitability and grants no runtime/broker authority.

## Classification vocabulary

- `REAL_IMPLEMENTATION_DEFECT`: strategy implementation materially fails the claimed mechanism/safety contract.
- `REGISTRY_DRIFT`: strategy exists but registry metadata/callable is stale or inconsistent.
- `AUDIT_SEMANTIC_ALIAS`: implementation consumes equivalent evidence under different field vocabulary; static audit label is false-positive/overliteral.
- `REQUIRES_BEHAVIORAL_PROBE`: static inspection is insufficient to establish structural validity.

## Confirmed triage

### vwap_orb — REAL_IMPLEMENTATION_DEFECT
Registry requires `trend_confirmation`. Implementation gates on VWAP displacement, dealer gamma, cumulative volume delta and VPIN but has no independent trend-confirmation input/state. The strategy name/contract therefore overstates the implemented confirmation structure.

### zero_hero_expiry — REGISTRY_DRIFT
Registry callable is `generate_signal`, while implementation exposes `zero_hero_strategy`. Strategy implementation exists; registry callable is stale.

### pairs_arbitrage — REAL_IMPLEMENTATION_DEFECT + AUDIT_SEMANTIC_ALIAS
The implementation computes a dynamic Kalman hedge ratio and performs an ADF stationarity test, so literal `beta_truth` and `cointegration_truth` findings are overliteral aliases. However, no explicit two-leg freshness contract is enforced. More importantly, ADF failure/import failure falls back to `kwargs.get('adf_pvalue', 0.04)`, which defaults to stationary and is fail-open. This is a real structural research defect.

### mean_reversion_extension — REAL_IMPLEMENTATION_DEFECT
Registry requires `oscillator_confirmation`; implementation uses range/chop score, VWAP extension, range boundary proximity and continuation pressure, but no oscillator confirmation. Either contract or implementation must be deliberately reconciled; until then structural repair is required.

### compression_breakout — REAL_IMPLEMENTATION_DEFECT
Implementation uses snapshot-derived `range_width_pct`, ATR ratio, support/resistance/ORB/day levels and current spot to infer compression and breakout. It does not independently prove an observed compression interval followed by a strictly later breakout from completed bars. Structural temporal evidence is weaker than the repaired ORB/Trend Pullback contracts.

### failed_breakout_trap — REAL_IMPLEMENTATION_DEFECT
Implementation relies on metadata assertions such as `previous_break_high`, `previous_break_low`, `price_reentered_range`, `failed_breakout_confirmed`, and `failed_breakdown_confirmed`. It does not independently reconstruct break -> failure -> re-entry from completed bars. This permits upstream assertions to substitute for causal temporal proof.

### late_day_momentum — AUDIT_SEMANTIC_ALIAS
Implementation directly consumes `minutes_since_open` and `minutes_to_close`, which are session-state evidence. Literal absence of `session_state` text is not a real defect.

### volatility_trend — AUDIT_SEMANTIC_ALIAS
Implementation consumes `cross_assets` and explicitly vetoes a trade if fewer than half of tracked cross-assets confirm the direction. Literal absence of `cross_asset_health` is not a real defect.

## Not yet structurally cleared

The following strategies require behavioral/adversarial probes before any `STRUCTURALLY_VALID` verdict: `ensemble`, `nifty_intraday`, `banknifty_intraday`, `sensex_intraday`, `opening_range_retest`, `trend_pullback`, `opening_drive`, `exhaustion_reversal`, `vwap_reclaim_rejection`, `option_pressure_confirmation`, `event_volatility_expansion`, `no_trade_chop`, and `pro_strategy`.

Existing dedicated temporal/causal evidence for Opening Range Retest and Trend Pullback may be reused, but must be pinned to exact source commit and executed natively before promotion from `STRUCTURALLY_VALID_WITH_LIMITATIONS`.

## Repair boundary

Repair only correctness/contract defects. Do not tune thresholds for profitability and do not reopen previously closed discovery domains. Any materially changed strategy implementation must receive a new source hash/version before bounded empirical testing.

Runtime authority: `NONE`.
Broker actions allowed: `false`.
Certification: `NOT_CERTIFIED`.

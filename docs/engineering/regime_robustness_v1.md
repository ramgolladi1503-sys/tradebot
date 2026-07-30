# Regime Robustness V1

## Verdict

`DETERMINISTIC_IMPLEMENTATION_READY_LIVE_CERTIFICATION_PENDING`

This branch repairs regime probability construction, entropy semantics, strategy-policy routing, scorer policy authority, and read-only evidence propagation without modifying feed, broker, order, execution, risk, tick-store, depth-store, or launcher modules.

## Defects repaired

1. Raw `oi_delta` could dominate regime logits; OI is now bounded using gross-OI ratio or a bounded fallback.
2. Missing required features could become numerical zero and create fake RANGE confidence; missing or invalid evidence now returns uniform probabilities, UNKNOWN, and fail-closed status.
3. IV scale was ambiguous; decimal and percentage IV normalize to one explicit decimal representation.
4. Six-decimal probability vectors may drift slightly from one; only vectors inside the existing `1e-5` contract are accepted and renormalized.
5. Unexpected non-zero regime labels are rejected.
6. The old additive heuristic produced near-uniform probabilities and persistent high entropy; V2 uses bounded structural supports for TREND, RANGE, RANGE_VOLATILE, EVENT, and PANIC.
7. Raw point-based VWAP slope and acceleration are ignored until ATR-normalized values are supplied.
8. Model source, hash, load/inference errors, feature quality, probability semantics, and calibration status are explicit.
9. JSON model inference requires its declared or inferred feature schema; incomplete feature sets fail closed.
10. Low entropy is no longer treated as a defect by itself.
11. Entropy interpretation is centralized; real probability vectors cannot use circular label-based TREND/RANGE overrides.
12. Real movement strategy IDs and legacy session labels now resolve to canonical policy families and buckets.
13. Session, entropy, trend confirmation, stable-regime status, liquidity, event, no-trade, and unknown-strategy policies are enforced.
14. Unknown strategies with regime context cannot inherit executable scorer buckets.
15. Existing snapshot regime truth is preserved through StrategyContext metadata, candidate evidence, and scoring policy without new feed reads or network calls.
16. Existing StrategyContext metadata is preserved, strategy-specific candidate evidence is merged rather than replaced, generated candidate lineage remains intact, and strict boolean values remain preserved.
17. Regime policy authority is scoped to canonical strategies, movement-strategy lineage, or explicit regime evidence. Generic scorer-only candidates without those signals retain the established scorer contract.
18. Explicit `NO_TRADE_ONLY` decisions remain no-trade decisions even when the no-trade policy itself returns BLOCKED; they are not mislabeled as generic suppression.
19. A completed-bar stabilizer exists with duplicate suppression, confirmation bars, dwell, and a high-evidence EVENT/PANIC fast path; it is not live-authoritative.

## Probability semantics

The repository has no tracked `models/regime_model.json`, so the default source is explicitly:

```text
HEURISTIC_STRUCTURAL_V2_UNCALIBRATED
```

Its distribution is a deterministic structural pseudo-probability. It supports entropy and policy diagnostics but is not claimed to be statistically calibrated.

Clear evidence should separate:

- strong ADX plus ATR/OI/depth alignment -> TREND;
- low ADX plus calm volatility/ATR -> RANGE;
- low ADX plus expanding volatility/ATR -> RANGE_VOLATILE;
- shock/uncertainty/IV expansion -> EVENT;
- shock plus volatility, ATR, transition, and normalized acceleration evidence -> PANIC.

Mixed structural evidence remains high entropy and fail-closed.

## Canonical strategy routing

Actual runtime IDs are mapped into policy families:

- opening/ORB IDs -> `OPENING_BREAKOUT`;
- mean-reversion, exhaustion, trap, and reversal IDs -> `MEAN_REVERSION`;
- pullback, VWAP reclaim, compression, late-day momentum, and option-pressure IDs -> `TREND_CONTINUATION`;
- event-volatility IDs -> `EVENT_VOLATILITY`;
- explicit no-trade IDs -> `NO_TRADE`.

Unknown strategies with explicit regime evidence resolve to ADVISORY_ONLY for low/normal entropy and BLOCKED for high/extreme entropy. Unknown movement-strategy lineage is also governed even when regime evidence is absent, so it cannot inherit executable scorer state.

Generic scorer-only fixtures and non-runtime candidates with no canonical strategy, no movement lineage, and no regime evidence remain outside regime-policy authority. This preserves the existing scorer contract without weakening runtime safety.

An explicit no-trade candidate remains `NO_TRADE_ONLY` with a zero score. Policy BLOCKED semantics for a no-trade strategy express intentional non-execution and must not convert that candidate into `SUPPRESSED_BY_DOWNGRADE`.

## Runtime safety boundary

The branch does not modify:

- `core/kite_depth_ws.py`;
- `core/feed/*`;
- `core/tick_store.py`;
- `core/depth_store.py`;
- broker/order/execution/risk paths;
- `run_live.sh`.

The probability and strategy-policy paths change on this branch. The stabilizer remains non-authoritative pending market-hours shadow proof.

## Canonical status semantics

- `VALID`: required features are complete and entropy is within the active session limit.
- `UNCERTAIN`: valid evidence exists but the structural distribution remains diffuse.
- `INSUFFICIENT_DATA`: required evidence is absent.
- `INVALID_INPUT`: evidence, probability vectors, or model schema is malformed.

Low entropy means concentration. It is not rejected unless paired with invalid or insufficient evidence.

## Deterministic certification

Focused suite:

```bash
PYTHONPATH=. pytest -q \
  tests/test_regime_robustness_v1.py \
  tests/test_strategy_regime_policy_v2.py \
  tests/test_strategy_regime_policy_scoring_v2.py \
  tests/test_regime_policy_context_propagation_v1.py
```

Certification runners:

```bash
PYTHONPATH=. python scripts/certify_regime_robustness_v1.py
PYTHONPATH=. python scripts/certify_strategy_regime_policy_v2.py
```

The focused suite contains 47 tests. The two runners contain 26 independent checks covering probability truth, structural separation, mixed-state uncertainty, model schema, policy aliases, session routing, unknown-strategy policy, and completed-bar hysteresis. The focused tests additionally prove both sides of scorer policy authority: runtime movement candidates remain fail-closed, while generic scorer-only candidates retain compatibility. The repository's existing opportunity-scoring tests prove explicit no-trade preservation. Final pass results must come from CI on the current branch head.

## Known integration limits

1. `core/market_data.py` still calculates the updated transition count after the current prediction; current-cycle transition-rate authority is not certified.
2. The current market-data caller does not yet supply ATR-normalized VWAP slope or acceleration, so raw cross-symbol values are intentionally ignored.
3. Expiry/event context propagation into every entropy caller still requires market-hours proof.
4. The completed-bar stabilizer is not live-authoritative.
5. Statistical calibration, predictive edge, and strategy profitability are not certified.
6. `ELIGIBLE_WITH_PENALTY` remains a policy classification; no arbitrary numerical score penalty was invented in this PR.

## Live certification still required

A market-hours observation must cover NIFTY, BANKNIFTY, and SENSEX and prove:

1. feed truth and subscription registry are unchanged;
2. feed callback latency and orchestrator cadence do not regress;
3. model provenance, probability semantics, feature quality, entropy threshold, and top-two margin are visible;
4. missing evidence never becomes confident RANGE;
5. no generic `entropy_too_low` rejection exists;
6. clear structural conditions do not remain permanently high entropy;
7. actual strategy IDs resolve to intended policy families;
8. invalid and unknown policy states remain non-executable;
9. candidate starvation changes only when evidence quality genuinely improves;
10. explicit no-trade candidates remain no-trade rather than generic suppression;
11. the stabilizer remains shadow-only until separately approved.

## Promotion rule

Do not merge as fully live-certified until broad CI and market-hours evidence are sealed. Deterministic certification proves implementation invariants, not predictive edge or live operational acceptance.

# Regime Robustness V1

## Verdict

`DETERMINISTIC_IMPLEMENTATION_READY_LIVE_CERTIFICATION_PENDING`

This branch repairs probability construction and entropy semantics without modifying feed, broker, order, execution, risk, tick-store, depth-store, or launcher modules.

## Defects repaired

1. Raw `oi_delta` could dominate the heuristic softmax. OI evidence is now bounded to `[-1, 1]`, using gross-OI ratio when available and a bounded fallback otherwise.
2. Absent required features could become numerical zero and create fake RANGE confidence. Absent or invalid required features now return uniform probabilities, `primary_regime=UNKNOWN`, and fail closed.
3. IV scale was ambiguous. Decimal IV and percentage IV are normalized to a decimal representation with explicit diagnostics.
4. Rounded probability vectors could drift slightly from one. Six-decimal vectors are accepted only inside the repository's existing `1e-5` tolerance and are renormalized before entropy calculation.
5. Unexpected non-zero regime labels were not rejected. Probability vectors now permit only the five canonical regimes.
6. The old additive heuristic gave every regime a large positive score, creating near-uniform probabilities and persistent high entropy. V2 uses bounded discriminative structural supports for TREND, RANGE, RANGE_VOLATILE, EVENT, and PANIC.
7. Raw VWAP slope and raw acceleration are not cross-symbol comparable. They are ignored unless the caller supplies ATR-normalized forms: `vwap_slope_atr` and `ltp_acceleration_atr`.
8. Model provenance was hidden. Output now records model source, path, SHA-256 hash, load errors, inference errors, feature quality, probability semantics, and whether probabilities are calibrated.
9. Trained-model inference could proceed with only a partial accidental feature match. Declared or inferred model features are now required; absent model features fail closed.
10. Low entropy was being discussed as if it were automatically unsafe. Low entropy is no longer a blocker by itself. It becomes suspicious only when feature quality is invalid or insufficient.
11. Entropy threshold ownership was duplicated. `RegimeProbModel.predict()` delegates uncertainty interpretation to the canonical entropy gate.
12. A completed-bar stabilizer now exists with duplicate-bar suppression, confirmation bars, minimum dwell, and a bounded EVENT/PANIC fast path.

## Probability semantics

The default repository has no tracked `models/regime_model.json`, so the active fallback is explicitly named:

```text
HEURISTIC_STRUCTURAL_V2_UNCALIBRATED
```

Its distribution is a deterministic structural pseudo-probability. It is suitable for entropy, separation, and routing diagnostics, but it is not claimed to be statistically calibrated.

Clear evidence is expected to separate:

- strong ADX + ATR/OI/depth alignment -> TREND;
- low ADX + calm volatility/ATR -> RANGE;
- low ADX + expanding volatility/ATR -> RANGE_VOLATILE;
- shock/uncertainty/IV expansion -> EVENT;
- shock + volatility + ATR + transition/normalized acceleration evidence -> PANIC.

Mixed structural evidence must remain high entropy and fail closed.

## Runtime safety boundary

The branch does not modify:

- `core/kite_depth_ws.py`
- `core/feed/*`
- `core/tick_store.py`
- `core/depth_store.py`
- broker/order/execution/risk code
- `run_live.sh`

The probability model and entropy gate change on this branch. The completed-bar stabilizer is implemented and tested but is not promoted as live routing authority. Promotion requires a market-hours shadow comparison.

## Canonical status semantics

- `VALID`: complete required features and entropy within the active session limit.
- `UNCERTAIN`: valid feature evidence but the structural distribution remains too diffuse.
- `INSUFFICIENT_DATA`: one or more required features are absent.
- `INVALID_INPUT`: required evidence or model schema is impossible or malformed.

Low entropy means a concentrated distribution. It is not rejected unless the concentration is paired with invalid or insufficient feature truth.

## Required deterministic certification

```bash
PYTHONPATH=. pytest -q tests/test_regime_robustness_v1.py
PYTHONPATH=. python scripts/certify_regime_robustness_v1.py
```

The focused suite contains 20 deterministic tests. The certification runner contains 15 independent checks covering:

- raw OI bounding;
- IV normalization;
- rounded-vector compatibility;
- unexpected-label rejection;
- absent/invalid feature fail-closed behavior;
- trained-model feature-schema enforcement;
- low-entropy semantics;
- invalid-vector rejection;
- raw-only legacy compatibility without probability-vector bypass;
- clear TREND, RANGE, RANGE_VOLATILE, and PANIC separation;
- mixed-structure uncertainty;
- uncalibrated heuristic provenance;
- completed-bar hysteresis.

No pass count is claimed until CI completes on the current branch head.

## Known integration limits

1. `core/market_data.py` still calculates the updated transition count after the current prediction; transition-rate authority is not certified in this PR.
2. The new provenance and feature-quality fields are returned by `RegimeProbModel`, but propagation into every live market snapshot requires a separate integration patch.
3. The current caller does not yet supply ATR-normalized VWAP slope or acceleration, so those raw cross-symbol inputs are intentionally ignored.
4. Expiry/event context propagation into every entropy caller still needs runtime proof.
5. Predictive edge and statistical probability calibration are not certified.

## Live certification still required

During a market-hours observation, record old and new regime outputs side by side for NIFTY, BANKNIFTY, and SENSEX. Acceptance requires:

1. Feed truth and subscription registry remain unchanged by the regime branch.
2. No increase in feed callback latency or orchestrator cycle stalls.
3. Model source, probability semantics, and feature-quality fields are visible on every regime decision.
4. Absent inputs produce `INSUFFICIENT_DATA` or `INVALID_INPUT`, never confident RANGE.
5. No generic `entropy_too_low` rejection exists.
6. High-entropy rejection contains raw entropy, normalized entropy, threshold, session bucket, probabilities, top-two margin, and feature-quality status.
7. Clear structural scenarios do not remain permanently high entropy.
8. Candidate starvation changes only when evidence becomes valid; no gate bypass is allowed.
9. The completed-bar stabilizer is evaluated in shadow before authority promotion.

## Promotion rule

Do not merge as fully live-certified until broad CI and the market-hours comparison are sealed. Deterministic certification proves implementation invariants, not predictive edge or live operational acceptance.

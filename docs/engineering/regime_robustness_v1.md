# Regime Robustness V1

## Verdict

`DETERMINISTIC_IMPLEMENTATION_READY_LIVE_CERTIFICATION_PENDING`

This branch repairs probability construction and entropy semantics without modifying feed, broker, order, execution, or risk modules.

## Defects repaired

1. Raw `oi_delta` could dominate the heuristic softmax. OI evidence is now bounded to `[-1, 1]`, using gross-OI ratio when available and a bounded fallback otherwise.
2. Missing required features could become numerical zero and create fake RANGE confidence. Missing or invalid required features now return uniform probabilities, `primary_regime=UNKNOWN`, and fail closed.
3. IV scale was ambiguous. Decimal IV and percentage IV are normalized to a decimal representation with explicit diagnostics.
4. Probability values were rounded before downstream diagnostics. Softmax now remains full precision and probability sums are validated tightly.
5. Model provenance was hidden. Output now records model source, path, SHA-256 hash, load errors, inference errors, and ignored features.
6. Low entropy was being discussed as if it were automatically unsafe. Low entropy is no longer a blocker by itself. It becomes suspicious only when feature quality is invalid or insufficient.
7. Entropy threshold ownership was duplicated. `RegimeProbModel.predict()` now delegates uncertainty interpretation to the canonical entropy gate.
8. A completed-bar stabilizer now exists with duplicate-bar suppression, confirmation bars, minimum dwell, and a bounded EVENT/PANIC fast path.

## Runtime safety boundary

The branch does not modify:

- `core/kite_depth_ws.py`
- `core/feed/*`
- `core/tick_store.py`
- `core/depth_store.py`
- broker/order/execution code
- `run_live.sh`

The stabilizer is implemented and deterministically tested but is not yet promoted as live routing authority. That promotion requires a market-hours shadow comparison.

## Canonical status semantics

- `VALID`: complete required features and entropy within the active session limit.
- `UNCERTAIN`: valid feature evidence but probability distribution remains too diffuse.
- `INSUFFICIENT_DATA`: one or more required features are absent.
- `INVALID_INPUT`: required evidence is impossible or malformed.

Low entropy means a concentrated probability distribution. It is not rejected unless the concentration is paired with invalid or insufficient feature truth.

## Required deterministic certification

```bash
PYTHONPATH=. pytest -q tests/test_regime_robustness_v1.py
PYTHONPATH=. python scripts/certify_regime_robustness_v1.py
```

Certification checks:

- raw OI cannot dominate the probability distribution;
- probability sums remain exact within floating-point tolerance;
- missing core features cannot fabricate RANGE confidence;
- non-positive ATR percentage fails closed;
- low entropy with valid evidence is not rejected;
- invalid probability vectors fail closed;
- duplicate bars do not advance transition confirmation;
- normal transitions require consecutive completed bars;
- EVENT/PANIC fast path requires high probability.

## Live certification still required

During a market-hours observation, record old and new regime outputs side by side for NIFTY, BANKNIFTY, and SENSEX. Acceptance requires:

1. Feed truth and subscription registry remain unchanged by the regime branch.
2. No increase in feed callback latency or orchestrator cycle stalls.
3. Model source and feature-quality fields are present on every regime decision.
4. Missing inputs produce `INSUFFICIENT_DATA` or `INVALID_INPUT`, never confident RANGE.
5. No generic `entropy_too_low` rejection exists.
6. High-entropy rejection contains raw entropy, normalized entropy, threshold, session bucket, probabilities, top-two margin, and feature-quality status.
7. Candidate starvation caused by regime is reduced only when evidence becomes valid; no gate bypass is allowed.
8. The completed-bar stabilizer is evaluated in shadow before authority promotion.

## Promotion rule

Do not merge as fully live-certified until the market-hours comparison is sealed. Deterministic certification proves implementation invariants, not predictive edge or live operational acceptance.

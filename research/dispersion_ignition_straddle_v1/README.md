# Dispersion Ignition Straddle V1

## Objective

Test an independent market process:

```text
constituent dispersion rises
+ directional participation becomes broad
+ NIFTY has not yet expressed equivalent movement
→ future NIFTY range expands
→ a same-strike ATM CE+PE purchase may beat costs
```

This is a magnitude hypothesis. It does not predict CE versus PE at signal time.

## Independence boundary

The campaign does not inherit any prior Market Event Graph sequence, direction,
threshold, state label, ranking, validation result, or holdout result. It reuses
only physical historical data and generic Python libraries.

## Frozen variants

1. High dispersion + high absolute participation + low index expression.
2. Rising dispersion + rising participation + low index expression.
3. High dispersion + broad movement without top-five concentration + low index expression.

All thresholds are computed from prior chronological training sessions only.

## Execution model

- completed five-minute constituent bar;
- nearest non-expired same-strike CE/PE pair within 100 NIFTY points of ATM;
- pair membership frozen before entry prices are accessed;
- both legs entered at the exact next one-minute open;
- fixed combined exits after 5, 10, 15, or 20 minutes;
- 0.50%, 1.00%, and 1.50% total-premium friction assumptions;
- stale signal-time option rows rejected;
- zero-volume rows reported and excluded from primary certification.

Historical bid/ask and IV are unavailable. The campaign therefore cannot claim
spread-certified execution or explain IV versus realised-movement attribution.

## Validation

- earliest 70% sessions: five expanding OOF folds;
- middle 15%: validation opened only for an OOF survivor;
- latest 15%: holdout opened only after validation passes;
- matched future-range controls;
- one-minute delayed-entry control;
- bootstrap, winner trimming, fold stability, and concentration gates;
- independent audit that does not import campaign logic.

## Verdicts

- `VALIDATED_DISPERSION_IGNITION_STRADDLE_EDGE`
- `UNDERLYING_RANGE_EDGE_ONLY_OPTION_TRANSLATION_FAILED`
- `NO_DISPERSION_IGNITION_STRUCTURAL_EDGE`
- `INSUFFICIENT_EVENT_OCCURRENCE`
- `INSUFFICIENT_CE_PE_PAIR_COVERAGE`
- `DATA_CONTRACT_BLOCKED`
- `INVALID_EVIDENCE_PIPELINE`

Research only. No broker calls, order actions, production registration, paper
authorization, or live authorization.

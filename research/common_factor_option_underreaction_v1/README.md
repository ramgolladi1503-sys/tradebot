# Common-Factor Option Underreaction V1

## Objective

Test whether a synchronized constituent common-factor shock reaches the selected
NIFTY option wing before the option has fully repriced.

```text
constituents move coherently in one direction
+ participation is broad
+ movement is not concentrated in a few names
+ NIFTY remains behind the constituent move
+ same-direction ATM option response remains weak
→ buy the same-direction option at the next minute
```

This is not the rejected dispersion-expansion hypothesis and does not reuse any
prior Market Event Graph state, direction, threshold, or result.

## Frozen candidates

1. Coherent common shock + index lag + selected-wing underreaction.
2. Broad common shock + low concentration + low premium burden.
3. Common shock + mirror-wing decay + selected-wing underreaction.

Direction is the sign of the completed constituent median return. It is frozen
before any entry or future option price is read.

## Replay

- nearest non-expired same-strike CE/PE pair within 100 NIFTY points of ATM;
- exact next one-minute open entry in CE for positive constituent median and PE
  for negative constituent median;
- fixed 5, 10, 15 and 20-minute exits;
- 1.0% primary and 1.5% severe total-premium friction;
- mirror-wing and additional one-minute-delay controls;
- chronological 70/15/15 research, validation and sealed holdout;
- five expanding OOF folds;
- training-only time-of-day and DTE-aware thresholds;
- bootstrap, top-winner removal and concentration gates.

Historical bid/ask and IV are unavailable. No spread-certified execution or IV
attribution is claimed.

## Verdicts

- `VALIDATED_COMMON_FACTOR_OPTION_UNDERREACTION_EDGE`
- `COMMON_FACTOR_DIRECTIONAL_EDGE_OPTION_TRANSLATION_FAILED`
- `NO_COMMON_FACTOR_OPTION_UNDERREACTION_EDGE`
- `INSUFFICIENT_COMMON_FACTOR_EVENT_OCCURRENCE`
- `INSUFFICIENT_DIRECTIONAL_OPTION_COVERAGE`
- `DATA_CONTRACT_BLOCKED`
- `INVALID_EVIDENCE_PIPELINE`

Research only. No broker call, order action, paper authorization, live
authorization, or production registration.

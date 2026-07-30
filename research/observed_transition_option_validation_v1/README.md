# Observed Transition Option Validation V1

This campaign begins only after Outcome-Blind Pattern Observation V1 froze recurring state transitions without reading outcomes.

## Frozen hypotheses

- `S0>S0 -> S1`: buy PE after the observed `S0>S0` prefix.
- `S3>S3 -> S2`: buy CE after the observed `S3>S3` prefix.
- `S1>S0 -> S0`: buy PE after the observed `S1>S0` prefix.
- `S2>S3 -> S3`: buy CE after the observed `S2>S3` prefix.
- `S0>S3 -> S0`: buy PE after the observed `S0>S3` prefix.

The predicted third state is never used for signal membership. Entry is the exact next one-minute open after the completed prefix. Primary exit is frozen at ten minutes. Primary friction is 1% of premium return.

The first half of the 77 previously unopened sessions is validation. The final half remains sealed unless at most one validation survivor passes all structural, economic, concentration, mirror-wing and delayed-entry gates.

Research only. No paper or live authorization.

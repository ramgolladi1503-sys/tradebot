# Agent Review Evidence — PR #806 Certifier Calibration V1

## Scope

Read-only calibration of the frozen PR #806 statistical certifier.

No strategy discovery, threshold relaxation, near-miss rescue, sealed-tail access, broker/order behavior, ranking, risk, paper/live authority, or production integration is permitted.

## Frozen evidence input

- artifact: `autonomous-structural-edge-exhaustion-v3`
- artifact ID: `9005119965`
- artifact SHA-256: `b00f8aeebc005112c6632a580a3123303c4aa1be64cc6158bfe244a55bb65b4a`
- expected Stage-6 semantic SHA-256: `2bdf60d6d7d463146f4ac11b4c9078ed04f2cee965d9629858660b1af34e6ae3`
- hypothesis count: `648`

The runner rejects the input if its artifact hash, hypothesis count, Stage-6 semantic hash, or allowed split contract differs.

Only observation / replication / validation events are accepted.

```text
SEALED_UNOPENED_LOADED=NO
SEALED_UNOPENED_SCORED=NO
```

## Calibration controls

1. Actual gate-attribution audit.
2. Dense +2/+5/+8/+15 bps planted effects.
3. Sparse planted effects: one hypothesis per each of 18 families, 200 deterministic trials per effect size.
4. 1,000 deterministic session-level Rademacher null worlds with observation-only direction reselection.
5. Diagnostic mean-targeting centered-bootstrap p-values under the unchanged 648-test BH denominator.
6. Explicit asymmetric-payoff control proving that positive expectancy is not equivalent to hit rate > 50%.
7. Representative synthetic plants passed through the existing Stage-6, Stage-7 WFA, and Stage-8 robustness functions. Stage 9 unopened test is not called.

## Initial result

```text
PR806_CERTIFIER_FUNCTIONAL_BUT_SPARSE_MODEST_EDGE_DETECTION_UNDERPOWERED
```

Key observations:

- 62 / 648 real hypotheses had positive replication CI90 lower bounds.
- 12 / 648 passed every Stage-6 gate except campaign-wide BH.
- minimum real BH q was approximately 0.3092.
- sparse +2 bps planted effects had 0% recovery.
- sparse +5 bps planted effects had approximately 3.83% mean recovery.
- sparse +8 bps planted effects had approximately 41% mean recovery.
- sparse +15 bps planted effects had approximately 91.97% mean recovery.
- one full Stage-6 false positive occurred across 1,000 diagnostic null worlds.
- a mean-targeting bootstrap diagnostic still produced zero BH survivors on the actual #806 corpus, so the sign-test mismatch alone does not rescue the frozen near misses.

## Claim boundary

This calibration may narrow interpretation of the #806 exhaustion claim, but it does not mutate the frozen #806 result.

It does not authorize:

- changing #806 gates;
- promoting any prior hypothesis;
- reopening failed families;
- accessing the sealed 63-session final tail;
- strategy integration;
- paper/live/order authority.

PR #809 remains a separate history-first discovery lane and is not modified by this branch.

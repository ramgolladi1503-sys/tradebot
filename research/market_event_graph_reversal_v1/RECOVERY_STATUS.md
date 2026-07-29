# Market Event Graph Recovery Status

## Recovered without retuning

The original evidence archive is `causal-market-state-v1-evidence-v3.zip` with SHA-256:

`fde3f5c74f12bf59d80d39012bffd89a9411954b9207561f92b792ade31099b3`

The frozen graph dataset has SHA-256:

`30f3d399404a299da6cb99b600a3f2b7346deb74653d5f4a8ebf8849ebefe73c`

Primary CE graph:

```text
breadth_down_1:HIGH
-> index_breadth_divergence:LOW
-> breadth_down_1:LOW
-> CE
```

Protocol recovered from the original report:

- chronological 60/20/20 split by session;
- graph semantics `A(t-2) -> B(t-1) -> C(t)`;
- `LOW` and `HIGH` derived from training-only 20th/80th percentiles;
- one-bar delayed entry;
- 15-bar holding period;
- 15-minute cooldown;
- 2 bps round-trip cost assumption.

Original CE evidence:

- training occurrences: 168;
- validation: 115 trades, mean 0.0005983524, win rate 0.6173913043, PF 2.4567905524;
- holdout: 25 trades, mean 0.0024606548, win rate 0.64, PF 4.1738554594.

Secondary PE graph is also preserved in `frozen_discovery_spec.json`.

## Merge blockers

This PR must not be merged as an edge-preserving implementation until all of the following are resolved:

1. Recover the exact numeric training 20th/80th percentile values from the frozen dataset.
2. Reproduce the original CE signal ledger and exact 115/25 split counts.
3. Enforce exact consecutive-row graph semantics `A(t-2), B(t-1), C(t)` rather than allowing arbitrary gaps between state-machine transitions.
4. Enforce the original 15-minute cooldown.
5. Keep the result shadow/advisory-only.
6. Do not claim option-premium validation because the original report contains `option_rows = 0`.

## Important implementation mismatch found

The current producer uses a persistent state machine:

```text
WAIT_HIGH -> WAIT_DIVERGENCE -> WAIT_LOW
```

That can accept events separated by arbitrary intervening bars. The recovered research protocol requires the three labels on exact consecutive rows. Therefore the current producer is not yet a faithful reproduction of the discovered edge.

## Prohibited actions

- Do not guess numerical thresholds.
- Do not re-run the 11,258-combination search to obtain replacement thresholds.
- Do not select thresholds from validation, holdout, July option data, or live data.
- Do not promote to auto execution.

Current truthful status:

`FROZEN_DISCOVERY_RECOVERED_REPRODUCTION_INCOMPLETE`

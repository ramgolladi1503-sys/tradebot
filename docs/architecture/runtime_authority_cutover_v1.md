# Runtime Authority Cutover V1

## Scope

This stacked post-PR763 change promotes one canonical execution authority into the actual candidate-selection, runtime-snapshot, operator-UI, and execution-router paths.

It does not modify market data, WebSocket subscriptions, feed recovery, persistence workers, Market Event Graph code, strategy formulas, ranking weights, risk thresholds, broker clients, or order placement.

## Authoritative flow

```text
candidate evidence
→ canonical executable truth
→ EXECUTABLE / ADVISORY_ONLY / BLOCKED
→ selection_score and capital firewall
→ legacy scorer receives EXECUTABLE candidates only
→ runtime snapshot and UI expose separate buckets
→ ExecutionRouter verifies authority again before approval/simulation
```

## Invariants

- fallback, recovered fallback, synthetic, unknown, stale, missing-spread, or contradictory candidates cannot execute;
- non-executable candidates retain diagnostic and opportunity scores;
- non-executable LIVE `selection_score` is zero;
- non-executable candidates receive zero capital and no portfolio slot;
- operator output separates `TOP_EXECUTABLE`, `ADVISORY_ONLY`, and `BLOCKED_DEBUG`;
- high confidence cannot override executable truth;
- the execution router rejects stamped non-executable candidates before approval or fill simulation;
- legacy unstamped tools/tests retain their existing behavior until they enter the cutover path;
- no order authority is introduced.

## Relationship to PRs #757 and #758

The immutable decision, runtime authority map, and ranking-authority taxonomy are retained from PR #757. The integrated tests absorb the useful PR #758 proof themes—purity, contradiction handling, stale/fallback blocking, object support, and protected feed boundaries—without adding a second competing authority contract.

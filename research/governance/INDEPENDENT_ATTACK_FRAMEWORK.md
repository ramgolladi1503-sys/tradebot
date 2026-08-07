# Independent Attack Framework

Independent attack exists to falsify, narrow, invalidate, or downgrade a claim before certification.

## Attack Principle

The attacker's job is not to improve the claim. The job is to find the strongest scientifically legitimate reason the claim should not be believed at its proposed authority level.

## Mandatory Attack Surfaces

1. Data provenance, gaps, survivorship, mapping, timestamp, and selection defects.
2. Leakage, look-ahead, label contamination, synchronization, and causal-order violations.
3. Multiplicity, researcher degrees of freedom, repeated tuning, and hidden search breadth.
4. Representation dependence, arbitrary bar construction, transforms, labels, thresholds, and sampling.
5. Statistical fragility, low power, unstable estimates, dependence, and inappropriate nulls.
6. Temporal, regime, instrument, and segment instability.
7. Mechanism alternatives and confounders.
8. Economic fragility under costs, spread, slippage, liquidity, capacity, and latency when economic claims are in scope.
9. Implementation mismatch between research and downstream operational consumption when operational promotion is in scope.
10. Reproduction by an independent procedure or reviewer where feasible.

## Severity

- `CRITICAL`: invalidates evidence or directly blocks the claimed lifecycle state.
- `MAJOR`: materially weakens scope or authority and must be adjudicated before certification.
- `MINOR`: does not currently block promotion but must be recorded.

## Outcomes

Each attack item is recorded as `SURVIVED`, `FAILED`, `UNRESOLVED`, or `NOT_APPLICABLE`, with evidence references.

A certification decision must explain every unresolved CRITICAL or MAJOR item. An unresolved CRITICAL item blocks certification.

## Independence

Independence means the attack is not merely the original analysis rephrased. At minimum, the attack should use a distinct falsification objective, and where feasible a distinct implementation, reviewer, representation, or data slice.

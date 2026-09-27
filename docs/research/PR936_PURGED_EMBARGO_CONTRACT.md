# PR #936 node G — purged and embargoed walk-forward contract

```text
source_agent: hermes
action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
title: Purge overlapping label windows and apply explicit time embargo
scope: Offline candidate_ml_v2 walk-forward fold construction and synthetic tests
requested_paths: core/analytics/candidate_ml_v2/dataset.py, core/analytics/candidate_ml_v2/certification.py, tests/test_candidate_ml_v2.py
allowed_paths: Those files and this contract only
forbidden_paths: Broker/order/risk/feed/live code, credentials, protected outcome data, ledgers, root dependencies, CI workflows, strategies
expected_tests: Synthetic labels crossing fold boundaries are excluded; explicit embargo is measured in epoch milliseconds; invalid negative controls fail closed; existing chronology remains valid
acceptance_proof: Focused splitter tests, full candidate_ml_v2 tests, offline analytics test set, exact commands/results recorded in acceptance log
```

## Design and invariant

The current candidate research splitter accepts `purge_rows` but does not use each row's `outcome_ts_epoch_ms` to establish whether its label has resolved before the test fold begins. A fixed row count is not a temporal guarantee when label horizons vary. For each chronological walk-forward fold, the nested train/validation split, and certification's feature-ablation validation partition, eligible training rows must therefore satisfy:

```text
outcome_ts_epoch_ms < first_test_decision_ts_epoch_ms - embargo_ms
```

The existing row purge remains an additional conservative control after interval filtering. `embargo_ms` is an explicit research certification configuration value in milliseconds, defaults to zero for API compatibility, and rejects negative values. The default preserves existing call signatures but intentionally tightens split membership by removing unresolved labels even when the embargo is zero. This can reduce training support and cause previously completing certification runs to fail closed. No test reads historical outcome stores; fixtures are synthetic and in-memory.

## Safety and limits

This changes offline fold construction only. It does not change feature generation, runtime wiring, strategy thresholds, trade execution, ledger access, or outcome authority. It does not implement combinatorial purged cross-validation or a post-test embargo for non-forward folds; the current splitter is expanding chronological walk-forward, where future observations are never in the training set. Research certification must configure a positive embargo from a predeclared horizon when needed. This is not evidence of independence, source fidelity, or a certified edge.

## Migration note

Callers may continue omitting `embargo_ms`; they receive the strict unresolved-label purge with a zero additional time gap. Certification owners should set a positive `CandidateMLCertificationConfig(embargo_ms=...)` from the frozen maximum label horizon plus any predeclared extra gap. Review resulting fold counts and training-session support before comparing reports across versions; metrics from older, unpurged splits are not directly comparable.

## Acceptance criteria

- A synthetic training row whose outcome timestamp reaches the first test decision is removed even with `purge_rows=0`.
- For positive `embargo_ms`, a synthetic training label resolving inside the embargo interval is removed and a label resolving outside it remains eligible.
- Feature-ablation training applies the same label cutoff, explicit embargo and configured row purge as the main certification folds.
- Nested model selection/calibration splits apply the configured embargo; certification fails closed if temporal purging leaves fewer than the configured minimum training sessions in any requested outer fold.
- Chronological disjointness remains true and invalid negative gaps raise an explicit `ValueError`.
- Full applicable analytics tests pass or their exact failure reason remains recorded; no test is skipped to improve the result.

## Execution declaration

GSD execution is limited to the paths named above. Required analytics test command covers `tests/analytics`, candidate ML v2 tests, and analytics store schema tests using synthetic fixtures and temporary directories only. No protected outcomes or runtime files may be opened.

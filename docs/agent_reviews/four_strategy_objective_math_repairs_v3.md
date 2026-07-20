# Four Strategy Objective Math Repairs v3

Audited baseline: `a48176fc245375f15e316493364915ec37439e29`

Integration source commit before bundle/evidence maintenance: `02ed107c9f6253736ea8ac564961e5121d77be42`

## Audit Artifact Hashes

```text
4694a2a40ce4e53ce868ff44b952c4aa8721e4fe5525ded0bcca2f84331a1fc4  objective_repairs_v2.json
a606b482154f9672f87fb72e0f713f734935ac4f5cee11aae40e45cfa757385a  design_decisions_required_v2.json
e486a6ffff53fa60d0fc610dff0691955fc211dd446c7b7348cd5937315c58f3  authority_register_v2.json
6099b1ed4d114b81cb7d26a5f3063e5a9baa506b7560fcfeb44599ef9da42cf0  four_strategy_authoritative_math_audit_v2.json
2d86e12ee2bd295320c7dfa40317eb536a4d9a0f3d05201f6c554a7b04d268a3  opening-range-retest/audit.json
6e024457a6efc62a34f3ee75f3b5ec953e81b35e9da3712bf335f271e63dac58  vwap-reclaim/audit.json
dbe8365c9b9c1f59d3ce37e33b58ad77f9f489e39ac53dbb65571b4610bf0de9  baseline_reconciliation.json
```

## Approved Human Decisions

ORB: `retest_distance_pct` must be calculated from `setup.retest_bar.close` to `setup.normalized_boundary_value`. `breakout_distance_pct` remains independently calculated from `setup.breakout_bar.close`.

VWAP: implemented behavior is `VWAP_RECLAIM_HOLD`. No rejection predicate is added. Compatibility identifiers `vwap_reclaim_rejection_v1` and `VWAP_RECLAIM_REJECTION` are preserved.

## ORB Repair

Before:

```text
retest_distance_pct = abs(setup.breakout_bar.close - setup.normalized_boundary_value) / abs(setup.normalized_boundary_value)
```

After:

```text
retest_distance_pct = abs(setup.retest_bar.close - setup.normalized_boundary_value) / abs(setup.normalized_boundary_value)
breakout_distance_pct = directional_distance(setup.breakout_bar.close, setup.normalized_boundary_value)
```

Temporal candidate presence changed: `NO`

Threshold/profile values changed: `NO`

Evidence changed: added `breakout_close`, `retest_close`, `continuation_close`, `retest_distance_source`, and `breakout_distance_source`.

Fingerprint impact: approved ORB raw-score fingerprint changes from `0.42150442477876104` in v1 bundle evidence to `0.54` in v2 bundle evidence.

Lane commit: `b2439e50565406bbf9910897294d23e67e7c307a`

## VWAP Repair

Before:

```text
confirmed_vwap_reclaim_or_rejection
confirmed VWAP reclaim/rejection in a non-chop regime
reclaim_rejection
```

After:

```text
confirmed_vwap_reclaim_hold
confirmed VWAP reclaim and hold in a non-chop regime
reclaim_hold
```

Predicate changed: `NO`

Score changed: `NO`

Rejection predicate added: `NO`

Threshold/profile values changed: `NO`

Fingerprint impact: approved `entry_trigger` and `rank_reason` text changed; raw score remains `0.392377`.

Lane commit: `1e39022558d5c2ed6d864d37a94db4b04236f7cc`

## Contract Bundle Evidence

V1 bundle byte-preservation hash:

```text
8b7df7e030306b9699347f9b3ed1c421fd8dfc302c7902a178e8111cb177d8c2  docs/agent_reviews/four_strategy_contract_bundle_v1.json
```

V2 bundle hash:

```text
3e6d2e653b606138688937197c9a9b682ec7d7611907a5be03c17e75e4d31844  docs/agent_reviews/four_strategy_contract_bundle_v2.json
bed09d869eb3d319c232efe4d3605de0c0314b0ee2ac1e689878be0b5439fc35  docs/agent_reviews/four_strategy_contract_bundle_v2.json.sha256
```

V2 bundle source commit uses the pre-bundle integration content identity `02ed107c9f6253736ea8ac564961e5121d77be42`, because the final integration commit includes evidence and contract files rather than additional production source edits.

## Validation

ORB lane:

```text
pytest -q tests/test_opening_range_retest_temporal_fixture_contract.py
python3 -m py_compile strategies/movement/opening_range_breakout.py tests/test_opening_range_retest_temporal_fixture_contract.py
ruff check strategies/movement/opening_range_breakout.py tests/test_opening_range_retest_temporal_fixture_contract.py
git diff --check
Result: PASS, 46 passed
```

VWAP lane:

```text
pytest -q tests/test_vwap_trap_movement_strategies.py
python3 -m py_compile strategies/movement/vwap_reclaim.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
ruff check strategies/movement/vwap_reclaim.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
git diff --check
Result: PASS, 11 passed
```

Integration:

```text
pytest -q tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_vwap_trap_movement_strategies.py tests/test_four_strategy_contract_freeze.py tests/test_four_strategy_contract_freeze_v2.py tests/test_strategy_parameter_profiles.py tests/test_movement_regime.py
python3 -m py_compile strategies/movement/opening_range_breakout.py strategies/movement/vwap_reclaim.py tests/test_four_strategy_contract_freeze_v2.py tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
ruff check strategies/movement/opening_range_breakout.py strategies/movement/vwap_reclaim.py tests/test_four_strategy_contract_freeze_v2.py tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
git diff --check
Result: PASS, 86 passed
```

## Scope Proof

Trend modified: `NO`

Compression modified: `NO`

Profile values changed: `NO`

Architecture added: `NO`

Design decisions beyond approval: `NO`

Broker API called: `NO`

Order action performed: `NO`

Backtest performed: `NO`

Forward returns calculated: `NO`

Pushed: `NO`

PR created: `NO`

Shared checkout `/Users/madhuram/tradebot` remained untouched and dirty with pre-existing changes.

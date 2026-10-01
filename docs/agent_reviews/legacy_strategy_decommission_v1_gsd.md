mode: READ_ONLY
candidate_id: legacy_strategy_decommission_v1_gsd
decision: PHASE_1_IMPLEMENTED_PENDING_CI
reason: Implement the approved Hermes deauthorization/invalidation contract without deleting physical legacy strategy modules.
timestamp: 2026-09-23T05:30:00+05:30
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
source: docs/agent_reviews/legacy_strategy_decommission_v1_gsd.md

# Legacy Strategy Decommission V1 — GSD Record

## Agent Work Contract

- source_agent: gsd
- action: GENERATE_PATCH
- title: Legacy strategy decommission phase 1 implementation
- scope: Apply the Hermes contract from `docs/agent_reviews/legacy_strategy_decommission_v1.md`.
- requested_paths:
  - strategies/strategy_registry.py
  - scripts/run_candidate_strategy_backtest.py
  - scripts/run_candidate_strategy_wfa.py
  - tests/test_strategy_registry.py
  - tests/test_candidate_strategy_backtest.py
  - tests/test_candidate_strategy_wfa.py
  - tests/test_legacy_strategy_decommission.py
  - docs/strategy_truth/legacy_strategy_tombstones_v1.json
  - docs/agent_reviews/legacy_strategy_decommission_v1.md
  - docs/agent_reviews/legacy_strategy_decommission_v1_gsd.md
- allowed_paths: exactly the files above
- forbidden_paths:
  - main.py
  - run_live.sh
  - config/**
  - credentials.py
  - core/execution*
  - core/broker*
  - core/order*
  - core/risk*
  - core/feed*
  - current frozen candidate specs
  - PR #930 runtime files
- expected_tests:
  - tests/test_strategy_registry.py
  - tests/test_legacy_strategy_decommission.py
  - required repository CI
- acceptance_proof:
  - final diff remains inside allowed files
  - removed synthetic runners stay absent
  - decommissioned IDs remain absent from old registry
  - MEG remains shadow-only
  - no current governed/frozen strategy implementation changed

## Scope Guard

Implemented changes are deliberately limited to legacy authority/evidence cleanup.

No broker, order, execution, risk, feed, credential, dashboard or live runtime path is changed.

No legacy implementation module is physically deleted in Phase 1.

No historical runtime artifact is rewritten.

Safety:

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
broker_write_authority=false
order_authority=false
ORDERS_PLACED=0
ORDERS_MODIFIED=0
ORDERS_CANCELLED=0
```

## Grill Me Review

Challenge: Could removal from `strategies/strategy_registry.py` disable the current live observer?

Answer: Current read-only live strategy declaration is `core/read_only_strategy_registry.py`, which is untouched. This PR removes entries from the older certification/audit registry only.

Challenge: Could deleting the synthetic scripts erase evidence?

Answer: No historical outputs are deleted. The scripts themselves are removed because their economic values were fixed constants. The tombstone records their invalidation.

Challenge: Did we remove generic safety tests?

Answer: No. Only the two dedicated artifact-shape tests for the removed synthetic runners are deleted. Shared safety/ranking/replay/observability tests remain.

GSD Grill Me verdict: PASS.

## Hermes Review

The implementation follows the two-phase architecture:
1. remove authority and invalid evidence generators;
2. separately delete physical implementations after dependency proof.

No Phase 2 physical deletion has been mixed into this patch.

Hermes conformance: PASS.

## GSD Review

Implemented:
- old registry reduced to MEG shadow/advisory entry, non-strategy helpers and test fixture;
- tombstoned strategy IDs removed from registry;
- synthetic legacy backtest runner removed;
- synthetic legacy WFA runner removed;
- their dedicated shallow tests removed;
- anti-resurrection test added;
- tombstone/invalidation manifest added.

Not implemented:
- physical deletion of movement/pro/ORB implementation files;
- removal of shared replay/ranking/safety fixtures;
- current strategy logic changes.

GSD verdict: IMPLEMENTED_PENDING_CI.

## QA / Safety Review

Static scope review:
- strategy threshold changes: none;
- broker/order changes: none;
- risk/feed changes: none;
- current read-only live strategy registry changes: none;
- current frozen candidate spec changes: none.

Focused behavioral assertions are located in:
- `tests/test_strategy_registry.py`
- `tests/test_legacy_strategy_decommission.py`

Repository candidate-safety and required CI must remain green on the final head.

QA/Safety verdict: PENDING_CI.

## Acceptance Proof

Expected focused command:

```bash
pytest -q tests/test_strategy_registry.py tests/test_legacy_strategy_decommission.py
```

Additional proof:
- Git diff against main contains only declared files;
- candidate-safety CI passes;
- required `unit_tests` and `health_gate` pass;
- non-required failures, if any, are documented and not bypassed.

## Runtime Proof Required After Merge

No live session is needed for Phase 1 because this patch removes legacy audit authority rather than adding runtime behavior.

Phase 2 requires a new dependency/reachability audit before physical strategy deletion.

## What This PR Does Not Prove

This PR does not prove:
- structural edge;
- profitability;
- execution viability;
- live readiness;
- that every physical legacy file is dead;
- that a data-blocked strategy is economically invalid.

It only proves authority/tooling cleanup if CI passes.

## Human Approval

The project owner explicitly authorized autonomous cleanup of negative legacy heuristic strategies, safe removal of their dedicated tests, and removal of the legacy backtest path. The implementation remains conservative: physical strategy files are not deleted until dependency-safe Phase 2.

## High-Risk Path Review

High-risk changed path:
- `strategies/strategy_registry.py`

The edit is removal-only with respect to trading strategy exposure. It cannot add broker/order authority. It preserves MEG as shadow/advisory-only and leaves the current live read-only registry untouched.

No other high-risk `strategies/**` implementation file is changed in Phase 1.

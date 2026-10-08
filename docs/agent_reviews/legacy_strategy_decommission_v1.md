mode: READ_ONLY
candidate_id: legacy_strategy_decommission_v1
decision: PHASE_1_DEAUTHORIZE_AND_INVALIDATE_SYNTHETIC_EVIDENCE
reason: Remove legacy strategy certification reachability and synthetic economic runners without changing current governed/live strategy behavior.
timestamp: 2026-09-23T05:30:00+05:30
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
source: docs/agent_reviews/legacy_strategy_decommission_v1.md

# Legacy Strategy Decommission V1

## Agent Work Contract

- source_agent: hermes
- action: DESIGN_ARCHITECTURE
- title: Legacy strategy decommission phase 1 — authority removal and synthetic backtest invalidation
- scope: Remove rejected/uncertified legacy strategies from the old certification registry, remove synthetic legacy backtest/WFA executables and their dedicated shallow tests, add tombstones and anti-resurrection coverage. Do not delete physical strategy implementation modules in this phase.
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
- allowed_paths: exactly the files listed above
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
  - core/runtime_safety_boot_guard.py
  - current frozen candidate specs
  - PR #930 runtime files
- expected_tests:
  - tests/test_strategy_registry.py
  - tests/test_legacy_strategy_decommission.py
  - candidate safety CI
  - required repository CI
- acceptance_proof:
  - decommissioned IDs absent from legacy certification registry
  - MEG remains shadow/advisory-only
  - helper/test-fixture registry behavior retained
  - synthetic backtest/WFA scripts removed
  - tombstone manifest present
  - anti-resurrection test present
  - no broker/order/risk/feed/live paths changed

## Scope Guard

This PR is registration/evidence cleanup only.

In scope:
- old certification registry authority;
- removal of two known synthetic economic runners;
- deletion of their two dedicated shallow artifact tests;
- tombstone and anti-resurrection evidence.

Out of scope:
- strategy threshold changes;
- current C1/C2/CAS/MEG implementation changes;
- current frozen prospective candidate changes;
- broker/order/risk/feed/live execution;
- physical deletion of legacy strategy implementations;
- rewriting historical runtime evidence.

Safety invariants:

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

Challenge: Are we deleting tests simply because strategies failed?

Answer: No. Only two tests whose sole purpose was to inspect artifacts from the synthetic economic runners are removed. Shared ranking, candidate-pool, observability, replay, safety, regime and execution-firewall tests remain untouched.

Challenge: Could a deleted legacy name still re-enter through the old certification registry?

Answer: The registry test and dedicated anti-resurrection test require all tombstoned IDs to be absent.

Challenge: Are historical reports being silently rewritten?

Answer: No. Existing runtime/research artifacts remain in place. The tombstone explicitly labels the two removed runners as invalidated evidence generators.

Challenge: Does this remove current MEG/CAS/C1/C2/frozen shadow work?

Answer: No. MEG remains explicitly shadow/advisory-only in the old registry. Current governed/frozen implementations are outside this PR.

Verdict: PASS for Phase 1 scope.

## Hermes Review

Architecture:

```text
historical legacy strategy code
        |
        v
old certification registry  --REMOVED AUTHORITY--> tombstone
        |
        X  rejected/uncertified entries no longer discoverable

synthetic backtest/WFA runner --DELETE--> historical artifacts retained
                                      \-> invalidation recorded
```

Phase 1 intentionally leaves physical strategy modules in place. That prevents accidental import breakage while authority is removed first.

Phase 2 may delete implementation files only after fresh call-graph/import evidence proves zero current governed/shadow/runtime dependency and Phase 1 CI is green.

Hermes verdict: PASS.

## GSD Review

Planned implementation is restricted to the declared files.

Required behavior:
- old registry becomes residual shadow/helper/test-fixture metadata only;
- rejected legacy IDs are absent;
- MEG remains non-certifiable shadow-only;
- synthetic backtest/WFA executables are absent;
- dedicated synthetic-artifact tests are absent;
- replacement tests prove decommission state.

No implementation file deletion is authorized by this Phase 1 contract.

GSD readiness verdict: PASS.

## QA / Safety Review

Required regression proof:
1. load_strategy_registry() cannot return a tombstoned strategy ID;
2. MARKET_EVENT_GRAPH_REVERSAL remains certification_supported=false;
3. helper entries remain not_certifiable;
4. TEST_STRAT remains test-only;
5. synthetic runner paths do not exist;
6. tombstone authority flags remain false;
7. repository candidate-safety checks remain green;
8. no changed path is a broker/order/risk/feed/live execution file.

No live/paper session is required for this cleanup.

QA/Safety verdict: PENDING_CI until GitHub checks complete.

## Acceptance Proof

Expected focused tests:

```bash
pytest -q tests/test_strategy_registry.py tests/test_legacy_strategy_decommission.py
```

Repository acceptance additionally requires required GitHub checks to pass on the final immutable PR head.

Changed-path acceptance:
- only declared Phase 1 files may differ from main;
- no strategy threshold or current frozen strategy spec may change.

## Runtime Proof Required After Merge

No live-market proof is required because this PR removes legacy authority and synthetic research tooling; it does not introduce runtime behavior.

After merge, Phase 2 must independently prove physical implementation reachability before deleting strategy modules.

The strongest allowed post-merge conclusion is:

`LEGACY_PHASE1_AUTHORITY_REMOVED_IMPLEMENTATIONS_PENDING_DEPENDENCY_SAFE_CLEANUP`

## What This PR Does Not Prove

This PR does not prove:
- any strategy is profitable;
- any legacy strategy failed for a particular numeric reason;
- structural edge certification;
- execution viability;
- live readiness;
- current governed strategy performance;
- that every physical legacy implementation is safe to delete.

## Human Approval

The project owner explicitly requested autonomous removal/decommission of the negative legacy heuristic strategies, their dedicated tests where safe, and the legacy synthetic backtest path. Physical implementation deletion remains gated by dependency evidence and CI rather than being performed blindly.

## High-Risk Path Review

High-risk changed path:
- `strategies/strategy_registry.py`

Review:
- this file is an old certification/audit registry, not the current read-only live strategy registry;
- the change only removes legacy entries;
- it does not add strategy logic;
- it does not change thresholds;
- it does not modify broker/order/risk/feed/live code;
- MEG remains shadow/advisory-only;
- current live read-only registry in `core/read_only_strategy_registry.py` is untouched.

High-risk verdict: bounded removal-only change; no runtime execution authority added.

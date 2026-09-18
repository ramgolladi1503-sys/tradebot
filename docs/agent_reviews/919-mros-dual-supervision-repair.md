# Governed Morning Observer Dual Supervision Repair (PR #919)

mode: SIM
candidate_id: 919-mros-dual-supervision-repair
decision: fix_morning_observer_dual_supervision_default_and_authority_wiring
reason: Fix zero-argument morning launcher default to dual supervision mode, serialize instrument date objects for reliable authority generation, and wire authority and master paths to MROS observer child process.
timestamp: 2026-09-18T04:10:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/919-mros-dual-supervision-repair.md

## Agent Work Contract

PR #919 only. Defaults morning observer launcher `run_governed_morning_observer_v1.py` to `DEFAULT_PRODUCTION_MODE = "dual"`, persists instrument authority with serializable date strings, and passes `--kite-instruments-file` and `--authority-artifact` to `run_market_event_graph_live_session_v1.py`.

## Scope Guard

In scope:
- `core/governed_morning_orchestrator.py`
- `scripts/run_governed_morning_observer_v1.py`
- `tests/test_governed_morning_orchestrator.py`
- `docs/agent_reviews/919-mros-dual-supervision-repair.md`

Out of scope:
- Live broker order routing, account trading execution, strategy threshold modifications, risk gate weakening, production kill switches.

## Grill Me Review

Verdict: PASS
Blocking issues: NO
Analysis:
- The entire pipeline operates in strictly read-only observation mode (`broker_write_authority = false`, `order_authority = false`).
- Zero broker trade authority: order placement, modification, and cancellation APIs are completely absent and forbidden.
- Dual supervision: Canonical launcher defaults to supervising BOTH `tick_data_collector.py` and `run_market_event_graph_live_session_v1.py`. Health of one cannot mask the failure of the other.

## Hermes Review

Verdict: PASS
Blocking issues: NO
Design Approach:
- Clean decoupling between launcher CLI defaults and orchestrator child process spawning.
- Passing authoritative dated instrument artifacts to the MROS observer ensures full gate compliance without runtime re-acquisition.

## GSD Review

Verdict: PASS
Blocking issues: NO
Implementation Status:
- All modified modules compiled cleanly with zero errors.
- Test suite in `tests/test_governed_morning_orchestrator.py` expanded with regression and attack tests covering zero-argument CLI defaults, instrument date serialization, and dual argument wiring.

## QA / Safety Review

Verdict: PASS
Blocking issues: NO
Testing and Boundaries:
- Unit tests: `tests/test_governed_morning_orchestrator.py` (44/44 passed).
- Compilation: `python3 -m compileall core scripts tests`.
- Boundaries: `is_order_action = false`, `broker_api_called = false`, `read_only = true`. Zero orders placed, modified, or cancelled.

## Acceptance Proof

```bash
pytest -v tests/test_governed_morning_orchestrator.py
python3 -m compileall core scripts tests
python3 scripts/validate_agent_review_evidence.py --base-ref origin/main --candidate-ref HEAD
```

## Runtime Proof Required After Merge

Run preflight verification:
```bash
python3 scripts/run_governed_morning_observer_v1.py --preflight-only
```

## What This PR Does Not Prove

This PR does not prove live trading profitability, alpha generation, or order execution fills. It provides hardened, governed, read-only observation infrastructure.

## Human Approval

Approved by human operator for merge, data capture automation, and governed read-only observation.

## High-Risk Path Review

Zero high-risk trading execution paths modified. Read-only observation orchestration only.

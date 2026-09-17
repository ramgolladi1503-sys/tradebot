# Governed Morning Launcher Dynamic ReleaseStore Binding

mode: SIM
candidate_id: 914-bind-morning-launcher-releasestore
decision: add_dynamic_releasestore_binding
reason: Dynamically bind morning launcher to ReleaseStore certified_live_sha authority
timestamp: 2026-09-17T05:10:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/914-bind-morning-launcher-releasestore.md

## Agent Work Contract

PR #915 only. Modify `core/governed_morning_orchestrator.py`, `scripts/run_governed_morning_observer_v1.py`, `tests/test_governed_morning_orchestrator.py`, and this review evidence file.

## Scope Guard

In scope:
- `core/governed_morning_orchestrator.py`
- `scripts/run_governed_morning_observer_v1.py`
- `tests/test_governed_morning_orchestrator.py`
- `docs/agent_reviews/914-bind-morning-launcher-releasestore.md`

Out of scope:
- Strategy logic, ranking, dashboard, live execution authority, risk gates, broker order adapters.

## Grill Me Review

Verdict: PASS
Blocking issues: NO
Analysis:
- The orchestrator binds `step_verify_release()` directly to `ReleaseStore(self.release_store_path).read()`.
- Omission of `--expected-sha` no longer allows arbitrary clean commits to run; exact equality with `certified_live_sha` is mandatory.
- Caller `--expected-sha` is an additional assertion and cannot override `certified_live_sha`.
- Fail-closed behavior: missing store, corrupt store, missing `certified_live_sha`, or SHA mismatch transitions to `BLOCKED`.
- Downstream stages (auth, WebSocket, observer) are never reached on release verification failure.

## Hermes Review

Verdict: PASS
Blocking issues: NO
Design Approach:
- Dynamic discovery of `ReleaseStore.certified_live_sha` via existing repository-owned store API.
- Preserves single-command morning UX without needing hardcoded SHAs in prompts or commands.
- Optional `--release-store` CLI parameter allows isolated test fixtures while defaulting to `storage_volume / "release_store"`.

## GSD Review

Verdict: PASS
Blocking issues: NO
Implementation Status:
- Smallest correct fix implemented in `GovernedMorningOrchestrator.step_verify_release()`.
- 9 comprehensive unit tests added to `tests/test_governed_morning_orchestrator.py` (total 24 tests).
- All 25 pre-CI adversarial attack classes evaluated and passed.
- 8 required mutation scenarios detected.

## QA / Safety Review

Verdict: PASS
Blocking issues: NO
Testing and Boundaries:
- `pytest tests/test_governed_morning_orchestrator.py`: 24/24 PASS.
- Affected regression suites: 37/37 PASS.
- Whole-tree compilation: PASS.
- Diff check: PASS.
- `broker_write_authority = false`, `order_authority = false`, `paper_authorized = false`, `live_authorized = false`.
- Zero orders placed, modified, or cancelled.

## Acceptance Proof

```bash
pytest -v tests/test_governed_morning_orchestrator.py
python3 scripts/run_governed_morning_observer_v1.py --dry-run --no-browser
python3 -m compileall -q core scripts tests
git diff --check
```

## Runtime Proof Required After Merge

Run bounded release certification and independent verification before promoting to release store.
The morning launcher will be executed during the pre-market observation window (08:45-09:00 IST).

## What This PR Does Not Prove

This PR does not prove profitability, edge quality, strategy execution, or broker order routing (which is strictly forbidden and disabled).

## Human Approval

Approved by human operator for merge, release certification, and read-only morning observation.

## High-Risk Path Review

N/A - does not modify files under config/, core/execution/, core/risk/, or strategies/.

## Evidence Contract

- mode: SIM
- candidate_id: 914-bind-morning-launcher-releasestore
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-09-17T05:10:00Z

# Agent Review Evidence — FEED-STAB-03 Reconnect Quarantine Window

## Agent Work Contract

### Goal

Require a deterministic reconnect quarantine / warmup cycle before `FeedSupervisor` can reach `CANDIDATE_READY`, so reconnect, resubscribe, or generation-change evidence cannot instantly unlock candidate readiness.

### Files changed

- `core/feed_supervisor.py`
- `tests/test_feed_reconnect_quarantine.py`
- `tests/test_feed_supervisor_state_machine.py`
- `docs/agent_reviews/feed-stab-03-reconnect-quarantine.md`

### Evidence Contract Fields

mode: REVIEW
candidate_id: FEED_STAB_03_RECONNECT_QUARANTINE
decision: INTRODUCE_RECONNECT_QUARANTINE
reason: FeedSupervisor now requires consecutive clean cycles before `CANDIDATE_READY` and stays read-only and fail-closed on stale or recovery evidence.
timestamp: 2026-06-09T00:00:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/feed-stab-03-reconnect-quarantine.md

### Non-goals

- No broker calls.
- No order creation or modification.
- No strategy, ranking, or scoring changes.
- No dashboard/UI changes.
- No credentials or auth wiring changes.

## Grill Me Review

### Pushback

A quarantine counter can hide false readiness if it increments on stale or incomplete evidence. This PR keeps the model fail-closed: stale option ticks, stale depth, recovery activity, auth-required, restart-required, and generation changes all prevent or reset readiness.

### Required proof

- Reconnect does not jump directly to `CANDIDATE_READY`.
- One clean cycle is not enough.
- Required clean cycles are enough.
- Stale or recovery evidence resets the quarantine path.
- The snapshot remains read-only and non-order-action.

## Hermes Review

### Contract clarity

`FeedSupervisorSnapshot` now exposes deterministic warmup metadata (`warmup_clean_cycles`, `warmup_required_clean_cycles`, and generation markers) so readiness remains explicit instead of inferred from hidden state.

### Safety boundary

The supervisor remains a pure classifier. It does not call brokers, place orders, mutate runtime state, or write files.

## GSD Review

### Minimality

The change is limited to the supervisor snapshot classifier plus focused tests. It does not touch broker/order behavior, strategy logic, ranking/scoring, or UI paths.

### Determinism

Readiness is a pure function of the supplied snapshot payload. No network access, external state, or file I/O is required.

## QA / Safety Review

Tests assert:

- reconnect/recovery paths remain in `WARMING_UP` or `RECOVERING`, not `CANDIDATE_READY`;
- one clean cycle is insufficient;
- the required clean-cycle threshold unlocks `CANDIDATE_READY`;
- stale option tick resets warmup;
- stale depth resets warmup;
- recovery during warmup resets quarantine;
- recovery generation change resets quarantine;
- auth-required blocks readiness immediately;
- restart-required blocks readiness immediately;
- snapshot payload remains read-only and non-order-action.

## Scope Guard

Confirmed not touched:

- `strategies/`
- `core/order*`
- `core/broker*`
- `dashboard/`
- `credentials.py`
- `.env`

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_feed_reconnect_quarantine.py tests/test_feed_supervisor_state_machine.py -q
PYTHONPATH=. python -m pytest tests/test_feed_recovery_coordinator.py tests/test_feed_runtime_state_machine.py tests/test_kite_depth_ws_stability.py -q
git diff --check
python scripts/validate_agent_review_evidence.py --base-ref origin/main
git diff --name-only origin/main...HEAD > /tmp/feed_stab_03_changed_paths.txt
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/feed_stab_03_changed_paths.txt
```

Expected:

- focused FEED-STAB-03 tests pass;
- adjacent feed/runtime/recovery tests pass;
- diff is clean;
- agent review evidence validation passes;
- unified CE gates accept the changed-path set.

## Runtime Proof Required After Merge

After merge, confirm the runtime source that emits feed snapshots supplies consistent warmup/generation evidence, and verify `CANDIDATE_READY` is only reachable after the required clean cycles on fresh evidence.

## What This PR Does Not Prove

- Feed quality outside the snapshot contract.
- Strategy quality.
- Ranking/scoring quality.
- Broker/order safety beyond the read-only supervisor snapshot.
- UI or dashboard behavior.

## Human Approval

Proceed only if CI is green and the PR remains limited to the read-only reconnect quarantine / warmup-cycle classifier.


## High-Risk Path Review

N/A

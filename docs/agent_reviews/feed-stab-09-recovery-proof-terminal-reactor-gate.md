# FEED-STAB-09 Recovery Proof Contract and Terminal Reactor Gate

mode: REVIEW
candidate_id: FEED_STAB_09_RECOVERY_PROOF_TERMINAL_REACTOR_GATE
decision: review_ready
reason: recovery_proof_terminal_reactor_gate
timestamp: 2026-06-09T06:30:00+05:30
source: feed_stab_09_recovery_proof_terminal_reactor_gate
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

Treat `ReactorNotRestartable` as terminal feed-runtime failure, persist restart-required evidence, and keep candidate readiness fail-closed on dead or stale feed evidence.

## Scope Guard

- No strategy logic changes.
- No ranking/scoring changes.
- No broker/order path changes.
- No dashboard/UI changes.
- No credentials changes.
- No runtime live probe artifact edits.
- No runtime log edits.
- No threshold relaxation.
- No fake readiness.

## Grill Me Review

This change must not hide a terminal runtime failure behind reconnect optimism. If the reactor cannot restart, the evidence must remain terminal and readiness must stay blocked.

## Hermes Review

The contracts remain pure/read-only classifiers. They only interpret supplied evidence and never call brokers, place orders, or mutate runtime state.

## GSD Review

Files changed are intentionally narrow:

- `core/feed_supervisor.py`
- `core/feed_runtime.py`
- `core/feed/runtime_store.py`
- `core/feed_readiness_for_candidates.py`
- `core/feed_soak_acceptance.py`
- `tests/test_feed_reconnect_quarantine.py`
- `tests/test_feed_readiness_for_candidates_contract.py`
- `tests/test_feed_soak_acceptance_contract.py`

## QA / Safety Review

Tests prove:

- `ReactorNotRestartable` and restart-required evidence remain terminal;
- `DEAD`, `NO_LIVE_OPTION_FEED`, and stale feed evidence block readiness;
- warmup resets on generation changes;
- consecutive clean cycles are still required for `CANDIDATE_READY`;
- soak acceptance fails closed on the bad-feed cases;
- snapshots remain read-only and non-action.

## Acceptance Proof

```bash
PYTHONPATH=. python -m pytest tests/test_feed_reconnect_quarantine.py tests/test_feed_readiness_for_candidates_contract.py tests/test_feed_soak_acceptance_contract.py -q
PYTHONPATH=. python -m pytest tests/test_feed_runtime_states.py tests/test_feed_truth_contract.py tests/test_kite_depth_restart.py -q
git diff --check
python scripts/validate_agent_review_evidence.py --base-ref ef5e502
```

Expected:

- focused feed recovery/proof tests pass;
- adjacent feed/runtime/restart tests pass;
- diff is clean;
- agent review evidence validation passes.

## Runtime Proof Required After Merge

After merge, the live feed source must continue to emit explicit restart-required evidence and must not promote `CANDIDATE_READY` under dead or stale feed conditions.

## What This PR Does Not Prove

- It does not make the feed self-heal from any network failure.
- It does not change strategy or ranking decisions.
- It does not change broker or order behavior.
- It does not modify dashboard/UI behavior.
- It does not touch live probe artifacts or runtime logs.

## Human Approval

Human review is required before merge because this is a terminal feed-recovery gate affecting live readiness evidence.

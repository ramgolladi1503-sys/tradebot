# PR877 Shutdown Signal Orchestration Review

mode: READ_ONLY
candidate_id: PR877
decision: MERGE_ONLY_AFTER_REQUIRED_CHECKS_PASS
reason: Restore graceful SIGTERM propagation into the existing fail-closed observation shutdown lifecycle without changing execution authority.
timestamp: 2026-09-01T16:21:00+05:30
is_order_action: false
broker_api_called: false
source: PR877_shutdown_signal_orchestration_review

## Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: Fix persistence shutdown signal orchestration
- scope: forward graceful SIGTERM to the read-only observer and enter its existing drain path
- requested_paths: `scripts/run_market_event_graph_live_session_v1.py`, `core/kite_read_only_observation_runtime.py`
- allowed_paths: the two requested runtime entrypoints and this review evidence
- forbidden_paths: broker/order/risk/CAS/auth/strategy/database paths
- expected_tests: focused orchestrator tests and Python compilation
- acceptance_proof: parent forwards SIGTERM; child requests lifecycle stop; existing fail-closed drain result remains authoritative

## Scope Guard

The change does not place orders, alter broker authority, enable CAS, change queue capacity, or mutate SQLite. The unrelated untracked runtime directory was not included.

## Grill Me Review

The repair must not be treated as durable-live proof. If persistence drain remains incomplete, the child still raises and no successful session seal may be claimed. A full fresh-session revalidation remains required.

## Hermes Review

The smallest source-grounded repair is signal orchestration at the parent/child boundary. The existing `ObservationLifecycle.shutdown()` remains the sole drain authority.

## GSD Review

Implemented on the PR877 branch. No strategy, CAS, feed subscription, or database behavior was changed.

## QA / Safety Review

Offline deterministic saturation reproduced explicit queue rejection and bounded incomplete shutdown. Python compilation passed. Focused orchestrator tests passed. No broker or live process was used.

## Acceptance Proof

Parent uses `Popen` and forwards SIGTERM to the child. Child installs a SIGTERM handler that requests lifecycle stop, allowing the existing `finally` block to execute drain, worker-join, and fail-closed completion checks.

## Runtime Proof Required After Merge

A new read-only session must demonstrate STOP_INGRESS, producer quiescence, zero post-quiesce enqueue, complete queue drain, SQLite commit, worker joins, and final seal. This PR does not provide that proof.

## What This PR Does Not Prove

It does not prove recovery of the 2026-09-01 session, zero persistence loss, CAS prospective support, structural edge certification, or live execution readiness.

## Human Approval

This narrow runtime repair requires human review and protected CI approval before merge.
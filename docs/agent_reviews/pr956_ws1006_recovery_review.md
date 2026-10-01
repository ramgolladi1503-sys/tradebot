# PR956 WS1006 Recovery Review

## Agent Work Contract
- source_agent: hermes -> gsd
- action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES, PLAN_PR, GENERATE_TESTS, GENERATE_PATCH
- title: Classify plain websocket 1006 disconnects consistently and preserve exact recovery proof
- scope: recovery reason classification and subscription-set proof for websocket reconnects.
- requested_paths: core/feed_recovery_coordinator.py, core/kite_depth_ws.py, tests/test_feed_recovery_coordinator.py, tests/test_kite_depth_ws_stability.py, docs/agent_reviews/.
- allowed_paths: listed files only.
- forbidden_paths: broker adapters/calls, order actions, risk gates, feed freshness gates, credentials, live configuration, strategies, and unrelated files.
- expected_tests: websocket stability and feed recovery coordinator tests, including shared classification, auth/terminal fail-closed behavior, and exact subscription-set proof.
- acceptance_proof: both classification layers agree on known plain 1006 reasons; auth and terminal reasons retain priority; proof expected tokens exactly match the selected resubscription set; ordinary unknown failures remain blocked.

## Scope Guard
A recoverable transport close may trigger only the existing bounded soft-reconnect path. Auth failures, terminal reactor failures, unknown errors, rate limits, and invalid proofs remain fail-closed. The proof must be bound to the token set selected for resubscription, and clear-recovery still requires actual subscription evidence plus fresh required-underlying ticks.

## Grill Me Review
- Failure mode: websocket reason wording changes and valid close code 1006 is classified as unknown in one layer. Addressed by shared reason classification and table-driven tests.
- Failure mode: reconnect subscribes to desired option tokens while the proof expects stale last-applied tokens. Addressed by deriving proof expectation from the same token-selection policy and reconciling actual tokens before recovery can clear.
- Remaining limitation: synthetic tests do not establish network reconnect behavior or real feed health.

## Hermes Review
Contract invariants: read_only=true; is_order_action=false; broker_api_called=false; allowed_for_live_execution=false. Recovery classification only selects an existing bounded reconnect path. Exact subscription token equality, required-underlying identity, pre-disconnect receipts, post-disconnect freshness, and mutation guards remain mandatory to clear recovery.

## GSD Review
The scoped patch centralizes plain WS1006 reason recognition so the coordinator and websocket handler cannot diverge. Tests cover standard close-reason variants, auth/terminal precedence, unknown errors, and desired-token proof alignment. No broker, order, risk, freshness, strategy, or live-mode code is changed.

## QA / Safety Review
- High-Risk Path Review: `core/kite_depth_ws.py` is a feed/WebSocket runtime path. Changes are restricted to classifying plain code-1006 transport reasons and binding existing recovery proof to the selected token set. Reconnect attempts remain bounded; existing subscription mutation guards and freshness gates are preserved. No broker API or order action is introduced.
- Unit evidence will be recorded after focused tests run.
- Runtime connectivity and same-session recovery evidence remain required after merge.

## Acceptance Proof
The test suite must prove every recognized plain WS1006 phrase maps to the same recoverable classification in both layers; auth and terminal cases do not become recoverable; unknown reason text remains blocked; reconnect proof expects precisely the policy-selected subscription tokens; and actual token mismatches keep proof invalid.

## Runtime Proof Required After Merge
Collect read-only evidence from a representative session: disconnect reason/code, selected and actual subscription token sets, bounded attempt count, required-underlying pre/post receipt timestamps, recovery verdict, and source SHA. Do not clear recovery based on connection status alone.

## What This PR Does Not Prove
It does not prove network stability, successful broker authentication, fresh production market data, sustainable reconnect behavior, order eligibility, paper/live readiness, or strategy quality.

## Human Approval
Human approval is required for merge. This review does not authorize broker calls, order actions, live-mode changes, or weakening any recovery or freshness gate.

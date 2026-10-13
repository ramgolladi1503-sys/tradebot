# PR #979 — Stale Generation Ticker Retirement

## Evidence Contract Fields

- mode: DEFENSIVE_FEED_LIFECYCLE_CLEANUP
- candidate_id: pr979-stale-generation-ticker-retirement
- decision: REVIEW_ONLY
- reason: Queue close of obsolete ticker instances that continue emitting generation-rejected tick callbacks.
- source_agent: gsd
- action: GENERATE_PATCH
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- append: false

## Agent Work Contract

- PR: #979
- Branch: `ram/fix-old-kite-protocol-retirement-20261013`
- Scope: On rejected stale-generation `on_ticks` callbacks, queue one reactor-thread close request for the captured obsolete ticker, with a second active-instance check under the ticker ownership lock. Correct the existing stale-option refresh test fixture so it models the intended connected state.
- Requested paths:
  - `core/kite_depth_ws.py`
  - `tests/test_kite_depth_restart.py`
  - `tests/test_kite_depth_ws_observation_on_ticks.py`
  - `docs/agent_reviews/pr979_stale_generation_ticker_retirement.md`
- Allowed paths: the four paths above only.
- Forbidden paths/behaviors: broker/order actions, credentials, secrets, live restart, strategy/risk/freshness policy changes, runtime threshold changes, weakening tests, claims of live readiness, or changes outside the allowed paths.
- Expected tests: stale ticker is closed once through reactor scheduling; active ticker is not closed; activation race is serialized; missing reactor fails closed; existing generation fence and observation-path tests remain green.
- Acceptance proof: focused tests, Python compilation, `git diff --check`, required PR checks reported by exact head SHA, and a later observed runtime proof for transport cleanup behavior.

## Scope Guard

Verdict: PASS

- Runtime behavior is limited to requesting cleanup after an obsolete instance is already rejected by the generation fence.
- The queued closure checks ticker identity again and holds the ownership lock across that check and the close request.
- If reactor scheduling is unavailable, cleanup is not attempted; an error event is logged.
- Logs explicitly state `transport_drained: false`; a close request is not presented as proof that the underlying transport has drained.
- No restart, subscription mutation, broker call, order action, execution/risk/strategy threshold, or feed freshness gate is changed.

## High-Risk Path Review

Verdict: PASS WITH RUNTIME PROOF REQUIRED

`core/kite_depth_ws.py` is a high-risk feed/WebSocket path. The change only closes a captured ticker after its callbacks are identified as stale and rejected. It is serialized with ownership changes. Local tests cover queue-once behavior, active-instance protection, and the identity-check/close race. Hosted `feed_smoke`, full unit tests, and exact-head governance checks remain necessary. Live transport drainage and absence of callbacks after closure are not established by unit tests.

## Grill Me Review

Verdict: PASS WITH HISTORICAL RCA UNKNOWN

The 15-minute captured window recorded 4,100 old-generation callback events. Existing callback generation checks rejected them; the event count alone does not prove a continuing transport leak. The available historical records do not bind those events to a ticker identity, socket state, close attempt, or transport completion, so the initiating lifecycle cause remains UNKNOWN. A Kite SDK source inspection showed that the prior helper's `disconnect()` fallback does not exist in the inspected SDK version, while `close()` behavior depends on its websocket reference; this is a plausible cleanup gap, not proof that it caused this session. This PR adds defensive retirement on observed stale callbacks and does not claim to resolve the unknown historical trigger.

## Hermes Review

Verdict: PASS WITH BOUNDED CONTRACT

Contract: stale callback processing remains rejected; it may request one serialized close of that callback's captured ticker only if that instance is not the active ticker both when checked and when the scheduled closure executes. Reactor-thread scheduling is used, and the ticker ownership lock is held through the final identity check and close request so concurrent activation cannot interleave. If scheduling is unavailable, the helper fails closed and logs the scheduling error. A successful close call is not transport-drain evidence.

## GSD Review

Verdict: PASS

The runtime patch adds a one-time queued retirement request and invokes it only from the stale-generation `on_ticks` rejection path. Regression tests cover active protection, duplicate suppression, deferred execution, reactor-unavailable behavior, and activation/close serialization. The stale-option test fixture now declares its intended one-window scenario and connected runtime state; separate existing tests retain the multi-window threshold coverage. No safety gate or threshold was weakened.

## QA / Safety Review

Verdict: PASS LOCALLY; HOSTED CHECKS MUST BE REPORTED AS OBSERVED

- Focused tests: `157 passed` across restart, generation-fence, and observation-on-ticks suites.
- `py_compile` passed for the changed Python files.
- `git diff --check` passed.
- No live process was restarted, no broker API was called, and no order action occurred.
- CI initially reported `agent-review-evidence` failed because this required document was absent; this file addresses that evidence requirement.
- CI reported `pr818-live-flow-freeze-target` failed because `core/kite_depth_ws.py` is in the frozen production surface. The user's instruction to ignore those checks is recorded as a waiver request, not a green result. All other hosted checks must still be inspected and reported individually.

## Acceptance Proof

Local validation performed against candidate commit `459545f5761435767688b5fac071f45cc23cac66` before adding this document:

```text
python3 -m pytest -q tests/test_kite_depth_restart.py tests/test_kite_depth_ws_callback_generation_fence.py tests/test_kite_depth_ws_observation_on_ticks.py
157 passed
python3 -m py_compile core/kite_depth_ws.py tests/test_kite_depth_restart.py tests/test_kite_depth_ws_observation_on_ticks.py
passed
git diff --check
passed
```

The final candidate SHA including this review document must be revalidated by hosted checks. Do not treat the earlier SHA's check results as validation of the updated candidate.

## Runtime Proof Required After Merge

During a later approved market session, observe whether stale-generation callbacks stop after the close request and whether the obsolete ticker's transport is actually drained. Bind evidence to ticker/socket identity, generation, close result, transport state, and subsequent callback count. If callbacks continue or transport state cannot be observed, record the result as unresolved and investigate the precise lifecycle cause. Do not restart the feed solely to produce this proof without separate authorization.

## What This PR Does Not Prove

1. It does not prove the exact historical cause of the old-generation callbacks; that RCA remains UNKNOWN.
2. It does not prove that `close()` drains the transport or prevents all later callbacks.
3. It does not establish live readiness, trading safety certification, strategy quality, or profitability.
4. It does not change policy for stale-option pruning, feed freshness, recovery guards, subscription budgets, or restart gating.
5. It does not turn any failed, skipped, waived, or pending hosted check into a pass.

## Human Approval

The user authorized the lifecycle scope to cover ownership state and the old/current ticker race. The user also directed that the PR818 check be ignored; that direction is documented as a waiver and does not change the check's result. This PR remains unavailable as a verified live-run candidate until the updated exact-head hosted checks and required human review/merge state are confirmed. No live restart is authorized by this document.

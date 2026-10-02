# Hermes → GSD Contract: MEG Live Volume Capture

## Hermes architecture and acceptance gates

**source_agent:** hermes
**action:** `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`
**title:** Preserve cumulative-volume truth in the isolated MEG live-source observer
**scope:** Kite packet volume forwarding and volume semantics in the MEG shadow OHLC buffer only.
**requested_paths:** `core/kite_depth_ws.py`, `core/market_event_graph_live_ohlc_buffer.py`, `core/ohlc_buffer.py`, focused tests, this contract.
**allowed_paths:** The requested paths only.
**forbidden_paths:** Broker/order/risk/strategy/configuration paths, credentials, runtime process state, and live execution behavior.

### Invariants

- Kite packet volume is a cumulative daily counter. It must never be summed as if it were a per-tick quantity.
- The observer derives nonnegative deltas per instrument token and attributes each observed delta to the source tick's minute. Deltas spanning observation gaps are estimates, not authoritative exchange minute volume.
- Every derived OHLC volume bar carries `volume_is_estimate=true` and `volume_attribution=CURRENT_SOURCE_TICK_MINUTE_ESTIMATE`; completeness means a valid cumulative baseline and uninterrupted valid deltas within that bar, not exact exchange minute allocation.
- First observation after reset, feed/day identity change, cumulative regression, missing, or invalid volume is incomplete. The OHLC bar volume is `null` if any constituent observation made it incomplete; never substitute zero for unknown.
- Invalid or unavailable volume must not reject an otherwise valid price tick.
- This data remains in the isolated MEG shadow buffer and cannot feed strategies, risk, or execution.
- Existing `OhlcBuffer` callers that do not explicitly provide volume-quality metadata retain their current behavior.

### GSD execution and verification

**source_agent:** gsd
**action:** `PLAN_PR`, `GENERATE_TESTS`, `GENERATE_PATCH`, `FIX_TEST_FAILURE`
**expected_tests:** Baseline then delta and repeated-value behavior; bar incompleteness; new-bar complete delta behavior; regression rebaseline; price acceptance on invalid/missing volume; ordinary OhlcBuffer compatibility; packet forwarding at the websocket observer callsite.
**acceptance_proof:** Focused MEG and websocket observer tests pass; no changes to strategy/broker/order/risk paths; diff and repository status reviewed.

### Migration and operations

No configuration keys or data migration are introduced. Consumers of MEG shadow bars must treat `volume: null` as unavailable and inspect `bar_provenance.volume_observation_complete`, `volume_delta_status`, `volume_attribution`, and `volume_is_estimate`. Re-run the focused tests in CI before accepting the patch. This does not certify live readiness or exact per-minute volume.

## Agent Work Contract

**source_agent:** hermes (design), then gsd (scoped execution)
**action:** `DEFINE_CONTRACT`, then `GENERATE_TESTS` and `GENERATE_PATCH`
**title:** Derive conservative estimated volume in the MEG shadow observer
**scope:** Forward Kite cumulative volume into isolated MEG OHLC observation and preserve uncertainty in buffer quality metadata.
**requested_paths:** `core/kite_depth_ws.py`, `core/market_event_graph_live_ohlc_buffer.py`, `core/ohlc_buffer.py`, focused tests, and this review document.
**allowed_paths:** These observer, buffer, test, and review-contract paths only.
**forbidden_paths:** Broker/order/risk/strategy/configuration paths, credentials, runtime process state, and live execution behavior.
**expected_tests:** Baseline/delta/reset/incomplete cases, price acceptance with unavailable volume, legacy buffer behavior, packet forwarding, and focused regression suite.
**acceptance_proof:** Unknown volume remains null/incomplete; estimated deltas carry explicit provenance; no live authority is introduced.

## Scope Guard

The volume delta is observational metadata in the MEG shadow path. It does not alter order, broker, strategy, risk, or live execution behavior. No config keys or migration are introduced, and normal `OhlcBuffer` callers without quality metadata retain existing semantics.

## High-Risk Path Review

`core/kite_depth_ws.py` is a WebSocket observer callsite. The only addition forwards a packet's cumulative volume value to the read-only MEG callback. It does not change connection, subscription, authentication, broker request, or order behavior. Invalid volume leaves valid price observations usable but marks volume uncertain; it is never replaced with a fabricated zero.

## Grill Me Review

Challenge: can a cumulative counter delta be misrepresented as exact minute volume? The metadata labels it as a current-source-tick-minute estimate; gaps mean allocation is not exact. Counter reset, first sample, missing or invalid samples yield incomplete/null volume. Downstream consumers must not treat the estimate as authoritative exchange volume or execution evidence.

## Hermes Review

Contract is explicit: cumulative values are differenced per token, re-baselined after day/session or reconnect generation changes, and uncertainty propagates to null volume. Price-tick acceptance is independent of volume validity. The observer stays isolated from strategy, risk, and execution.

## GSD Review

Scoped implementation and tests cover cumulative forwarding, delta and repeated-value behavior, reset/incomplete cases, new-bar attribution, invalid-volume price acceptance, and legacy buffer compatibility. The patch changes no forbidden paths.

## QA / Safety Review

Volume is not promoted into execution authority. Unknown is represented as null/incomplete, and estimated attribution is labeled. No broker API or order action is performed. Full local suite passed at the candidate SHA; exact-head CI remains the PR acceptance gate.

## Acceptance Proof

Candidate SHA `5c2292ead5bd81396228431d01ae27a398d2c8e9`: full suite 8,553 passed, 9 skipped, 28 deselected; final focused regression set 93 passed; `py_compile` and `git diff --check` passed. GitHub exact-head checks are tracked on PR #958.

## Runtime Proof Required After Merge

Any post-merge check must be read-only and verify raw cumulative values, reset/reconnect handling, null completeness, and estimate labels across captured market data. Do not modify live processes or connect this observer to execution as part of runtime verification.

## What This PR Does Not Prove

It does not prove exact exchange minute volume, sustained feed health, strategy value, or paper/live readiness. Gaps in cumulative observations limit minute attribution, and that limitation remains explicit.

## Human Approval

No approval is granted to use these estimates for strategy, risk, or execution decisions. Such runtime wiring requires a separately scoped and explicitly approved change.

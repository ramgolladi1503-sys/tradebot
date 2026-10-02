# MEG Interval Mismatch Diagnostics Review

## Agent Work Contract

```text
source_agent: hermes (design), then gsd (scoped execution)
action: DEFINE_CONTRACT then GENERATE_PATCH
title: Preserve fail-closed MEG interval rejection with endpoint evidence
scope: add diagnostic context to INDEX_INTERVAL_MISALIGNED rejection records
requested_paths:
  - core/market_event_graph_live_runtime_bridge.py
  - tests/test_market_event_graph_live_runtime_bridge.py
  - tests/test_market_event_graph_bridge_interval_state_machine.py
  - docs/agent_reviews/meg-interval-mismatch-diagnostics.md
allowed_paths: the four requested paths only
forbidden_paths: broker/order/risk/strategy paths, credentials, live runtime state, feed freshness policy
expected_tests: focused MEG bridge tests; diff check; agent review evidence gate
acceptance_proof: mismatch remains rejected and records index/constituent endpoints, delta, cycle cutoff and latest live tick timestamps
```

## Scope Guard

The change adds RCA fields to the existing mismatch rejection. It preserves exact
bar-end equality, `INDEX_INTERVAL_MISALIGNED`, and non-export behavior. It does not
align bars, forward-fill prices, change freshness thresholds, or infer synchronized
market data from receipt time.

## Grill Me Review

Diagnostic endpoints improve the next live run's evidence but do not identify the
cause of the observed mismatch or repair data synchronization. The current patch
must not be described as resolving the underlying runtime issue.

## Hermes Review

Contract: a snapshot is exportable only when index and all constituent bars have
the same finite source bar-end epoch and valid live provenance. On mismatch,
reject unchanged and include the two symbols, endpoints, signed delta, cycle
cutoff, and last live tick epochs when available. Missing or non-finite values
remain null; they never satisfy the synchronization contract.

## GSD Review

The runtime bridge and its focused tests are the only implementation paths. One
state-machine test is updated for the private snapshot helper's expanded return
tuple. No runtime wiring, order, broker, strategy, freshness, or risk logic changed.

## QA / Safety Review

- Mismatched epochs remain blocked and unexported.
- Evidence remains read-only; `is_order_action=false`, `broker_api_called=false`,
  and `allowed_for_live_execution=false` remain present.
- Focused tests verify returned and persisted diagnostic fields.
- Local validation: 22 focused MEG bridge tests passed; `git diff --check` clean.

## High-Risk Path Review

The bridge is runtime market-data code. The patch changes only diagnostics on the
existing rejection path; it does not change source selection or acceptance
criteria. Any diagnostic write failure remains isolated from the fail-closed
rejection result.

## Acceptance Proof

An exact 60-second endpoint mismatch remains rejected with no export, while the
audit result and rejection JSONL carry both endpoint epochs, the signed delta,
cycle cutoff, and last live tick epochs. Non-finite source epochs are not accepted.

## Runtime Proof Required After Merge

In a separately authorized read-only live observation, confirm the next mismatch
record contains the source endpoints and last-tick timestamps. Do not infer that
this instrumentation fixes the mismatch; use the added evidence to establish a
separate root cause and narrowly scoped remediation.

## What This PR Does Not Prove

It does not prove why the live bars were misaligned, that historical bars can be
safely aligned, feed health, trading edge, or paper/live readiness.

## Human Approval

No merge, live configuration change, broker call, order action, or execution
authorization is included or implied.

# Full Live Multi-Cycle MEG Repair Review

## Scope

- Repair branch: `fix/full-live-multicycle-meg-and-feed-stall-v1`
- Failed authority: `facdf49f080d79133fc7544393acfea8f9486747`
- Scope: cycle-scoped selected-tick evidence only.
- Feed watchdog/reconnect behavior was not changed because the sealed failure
  root did not contain enough callback, persistence, or watchdog evidence to
  localize that defect safely.

## Agent Work Contract

- source_agent: Codex
- action: surgical offline repair
- title: fresh selected-tick evidence per MEG cycle
- requested_paths: the three runtime files and focused causality tests listed above
- allowed_paths: those runtime files, focused tests, and this review record
- forbidden_paths: main, dirty checkout, credentials, broker/order/risk behavior,
  feed watchdog policy, and sealed live evidence
- expected_tests: focused multi-cycle controls, eight MEG shadow gates, compile,
  diff check, and agent review evidence

## Scope Guard

The implementation is restricted to request/cycle evidence provenance. It does
not alter candidate generation, ranking, execution routing, risk gates,
credentials, broker adapters, or reconnect thresholds.

## Grill Me Review

The failed live root derived 51 unique selected tick IDs from 153 rows. Each
identity appeared in three accepted cycles, producing 102 duplicate rows. The
repair does not weaken the verifier or synthesize IDs. It records the latest
eligible callback tick and rejects a reused, missing, or future tick.

## Hermes Review

Request scope establishes eligibility and generation ownership. Cycle scope
selects the latest eligible tick at or before the cycle cutoff. Reconnect or a
new subscription clears the eligible selection. Accepted cycles fail closed if
any required token has no fresh eligible tick.

## GSD Review

Changed runtime files are limited to `core/kite_depth_ws.py`,
`core/kite_read_only_observation_runtime.py`, and
`core/meg_request_scoped_causality.py`. Tests add a 51-token, three-cycle proof
and negative controls for stale and future ticks. No broker, order, risk,
strategy, or watchdog behavior was changed.

## QA / Safety Review

- Focused causality/lifecycle tests: 14 passed.
- Eight-gate MEG shadow verifier: passed on the repair commit before this
  review record was added; it must be rerun on the final commit.
- `git diff --check`: passed.
- `compileall`: passed, with pre-existing syntax warnings only.
- Broker write authority: false.
- Order authority: false.
- Live/paper execution authorization: false.

## High-Risk Path Review

`core/kite_depth_ws.py` is a feed/WebSocket path. The change only records and
resets the latest eligible tick identity already observed by the callback. It
does not change connection, subscription, restart, watchdog, or broker-call
control flow. The selected evidence writer fails closed on stale, missing, or
future cycle data.

## Acceptance Proof

The deterministic 51-token, three-cycle fixture proves 153 selected rows with
zero selected-tick ID reuse. Stale-cycle and future-tick controls fail closed.
The final committed SHA must be rerun through the eight-gate verifier before
any live retry.

## Runtime Proof Required After Merge

A fresh governed read-only session must produce at least three MEG cycles with
zero selected-tick reuse and advancing callback/persistence/watchdog evidence.
This repair is not live-certified by offline tests.

## What This PR Does Not Prove

It does not prove feed availability, broker connectivity, strategy edge,
profitability, fill quality, execution viability, or paper/live readiness.

## Human Approval

Human approval is required before any new live observation. No merge to main or
execution authority change is authorized by this repair.

## Remaining limitation

The sealed session cannot distinguish broker silence from callback or evidence
writer failure. A future live campaign must add explicit callback, persistence,
and watchdog progression checks and require at least three MEG cycles.

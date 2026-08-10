# Full Live Multi-Cycle MEG Repair Review

## Scope

- Repair branch: `fix/full-live-multicycle-meg-and-feed-stall-v1`
- Failed authority: `facdf49f080d79133fc7544393acfea8f9486747`
- Scope: cycle-scoped selected-tick evidence only.
- Feed watchdog/reconnect behavior was not changed because the sealed failure
  root did not contain enough callback, persistence, or watchdog evidence to
  localize that defect safely.

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

## Remaining limitation

The sealed session cannot distinguish broker silence from callback or evidence
writer failure. A future live campaign must add explicit callback, persistence,
and watchdog progression checks and require at least three MEG cycles.

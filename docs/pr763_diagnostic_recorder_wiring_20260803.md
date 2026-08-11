# PR #763 Diagnostic Recorder Wiring Diagnosis

## Prior proof defect

The reported August 3 proof was not sufficient to establish fresh diagnostic
evidence. Its root was already sealed and its diagnostic streams were empty.
The launcher generated run IDs from the composition manifest rather than the
campaign commit, created roots with `exist_ok=True`, and did not independently
record or verify the child commit. Runtime rows also used the PR #750 source
commit field, which is not the campaign implementation SHA.

## Repair

Normal launches now use the session date, the current campaign commit prefix,
and a cryptographically strong nonce. Root creation fails with
`RUN_ROOT_ALREADY_EXISTS`; no implicit resume or overwrite is possible. The
child independently computes `git rev-parse HEAD` and fails closed on a SHA
mismatch.

The active child starts the bounded campaign diagnostic recorder, records
observer/recorder relationships, and persists a marked diagnostic self-test to
the same run root. The self-test only writes diagnostic streams; it does not
invoke feed callbacks, canonical stores, MEG, candidate generation, risk, or
execution.

## Proof

Presession run:
`unified-pr748-756-20260803-75f259e3c72b-presession-wiring-presession-2`

It returned `READY_FOR_LIVE_START` with no blockers,
`diagnostic_self_test_passed=true`, and
`wiring_registry_complete=true`. No new governed live run was started in this
repair step. The prior run root remains untouched.

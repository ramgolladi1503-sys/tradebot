# PR #763 Reactor Stall and False Seal Diagnosis

The sealed run's callback maximum and reactor drift are real monotonic-time
measurements. Both are recorded on the Kite reactor thread; process heartbeats
continue while reactor heartbeats become sparse. Entry and exit counts remain
paired and the bounded diagnostic queue does not show overflow. The artifacts
prove reactor starvation, but do not identify one synchronous operation with
enough span detail to justify changing the feed callback path. No feed-path
repair is made here.

The terminal `FAILED_SEAL` was a custodian classification defect. The
custodian-owned SIGTERM produced exit code `-15`, the child exit was
acknowledged, the exact manifest was verified, and `SEALED` was created. That
is an expected signal exit, not a seal failure. The custodian now reports
`SEALED_SUCCESS` only for an owned SIGTERM plus verified sealing, while
unowned nonzero exits remain failures.

The final launcher process-identity write also replaced the child observer's
`child_observed_sha`. The final write now preserves the existing identity
fields so expected, observed, and manifest commits remain auditable.

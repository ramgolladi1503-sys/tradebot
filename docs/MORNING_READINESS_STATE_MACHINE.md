# Morning Readiness V1 state machine

This is the fail-closed readiness foundation for the master morning workflow.
It models explicit release, pre-open, live, degraded, drain, and seal states.

The observation plane may continue in `LIVE_DEGRADED` for non-fatal option,
ranking, strategy, or CAS-input failures. Storage authority, evidence
integrity, queue-loss, process-integrity, and authority-escalation failures
transition to `FAIL_CLOSED`.

The module never grants broker-write, order, paper, or live-execution authority.
The full one-command launcher, independent verifier, fresh-root creator, and
automatic EOD supervisor remain separate certification gates and are not implied
by this state machine alone.

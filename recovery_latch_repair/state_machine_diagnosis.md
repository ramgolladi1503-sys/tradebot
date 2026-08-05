# Partial-Recovery Latch Diagnosis

Principal cause: `PARTIAL_RECOVERY_MISCLASSIFIED_AS_TERMINAL`.

The watchdog classified a callback window with some stale tokens as
`partial_activity_detected`, then allowed the provisional `partial_recovery`
marker to remain indistinguishable from a terminal blocker. Downstream runtime
truth converted that marker into `RECOVERY_BLOCKED` and
`process_restart_required=true`, even though later callbacks were present.

The repair clears only the provisional marker when the reactor has not
independently entered a terminal state. It does not clear a reactor-terminal
marker, disable stale detection, or remove bounded restart protection.

Recovery contract: partial batches remain degraded/verification-pending;
stable fresh batches use the existing configured quorum and stable-cycle
requirements; only confirmed recovery clears the error and latch; exhausted or
reactor-terminal recovery remains fail-closed.

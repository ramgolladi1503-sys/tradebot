# Captured Timeline Replay

The deterministic replay uses the captured shape: 73-token subscription,
initial full activity, a stale window, a partial resumed batch, then stable
fresh batches. The repaired state machine remains provisional after the partial
batch and returns to `LIVE` after the configured stable-cycle confirmation.

Negative control: with the reactor-terminal marker set, partial callbacks do
not clear the blocker and recovery remains fail-closed.

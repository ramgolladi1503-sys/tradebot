# Pre-Fix Root Cause

Verdict: `RCA_PARTIALLY_CONFIRMED`.

The permanent blocking defect is confirmed: `_maybe_trigger_silent_reconnect()` converts partial activity into the terminal `partial_recovery` reconnect latch. `_normalize_recovery_blocked_snapshot_state()` then reports `RECOVERY_BLOCKED` and rewrites effective websocket connectivity to false even while `on_ticks` continues receiving fresh callbacks. The latch clears only when every tracked token becomes fresh (`stale_tokens == 0`), so one persistently silent token can suppress recovery indefinitely.

The six-token application cause is not confirmed. Startup requested 73 total tokens (3 underlying plus 70 options) and synchronously invoked both subscribe and `MODE_FULL`. Sixty-four options produced ticks; six systematic outermost-low CE/PE contracts produced none. Historical code persisted no callback-confirmed applied registry, no `MODE_FULL` applied registry, and no socket generation. It is therefore unsafe to claim those six were not subscribed.

The historical 70-token verification field is mislabeled desired/requested inventory. Its `OK` state only proves at least one post-start option tick per required symbol, not token-complete subscription or freshness. Treating it as active-subscription proof violates `verified active subscriptions <= callback-confirmed applied subscriptions`; the latter did not exist.

Physical transport and execution safety were also conflated. Tick callbacks prove the transport remained active after canonical snapshots reported `ws_connected=false`. The truthful state was: transport callbacks active, subscription registry inconsistent/unknown, execution feed not ready, canonical safety state `RECOVERY_BLOCKED`.

This change adds generation-gated mutation callbacks and explicit requested, queued, callback-applied, callback-failed, old-generation-ignored, socket-generation-started, and registry-snapshot events. It deliberately does not clear `partial_recovery` or perform token-local resubscription before a new instrumented run resolves the six-token ambiguity.

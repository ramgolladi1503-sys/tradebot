# Instrumented Startup Summary

Evidence directory: `runtime/diagnostics/feed_subscription_startup_20260730T084905Z`

The LIVE startup used `bash scripts/run_feed_freshness_instrumented_live.sh`, which delegated to `run_live.sh --skip-login` and then `python main.py`. The observed process identity was wrapper PID `32950` and main PID `33107`. The run was on branch `fix/feed-freshness-recovery-v1` at commit `f2d5b53598c240b833288593cfb42457b3b3c7b9`.

Startup truth:

- Runtime mode: `LIVE`
- Socket generation: `1`
- Desired tokens: `73`
- Subscribe requested: `73`
- Subscribe callback-applied: `73`
- MODE_FULL requested: `73`
- MODE_FULL callback-applied: `73`
- Unique persisted tick tokens: `73`
- Unique persisted depth tokens: `70`

The six historically suspected zero-tick contracts, `15116034`, `15116290`, `16816386`, `16816642`, `292810245`, and `293652741`, were absent from the current desired inventory. Their classification for this startup is `SUBSCRIBE_NOT_REQUESTED`. They are not current subscription failures and are not used as repair targets.

The confirmed defect was the terminal latch: after complete callback-applied subscription and MODE_FULL truth, the runtime observed partial activity, set `reconnect_blocked_reason=partial_recovery`, emitted `RECOVERY_BLOCKED`, forced canonical `ws_connected=false`, and marked the downstream feed unavailable even though tick callbacks continued.

Implementation decision: repair the false permanent partial-recovery latch. Do not implement recovery logic specifically for the six historical contracts.

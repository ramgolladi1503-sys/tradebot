# Startup Mode Root Cause

Verdict: `BLOCKED_BY_INSTRUMENTED_STARTUP_MODE`

The prior instrumented process did not provide WebSocket subscription evidence because it ran as `SIM`. It never reached Kite WebSocket construction, socket generation, subscribe request, `MODE_FULL` request, tick callback, or depth callback.

## Exact Cause

The failed instrumented startup was launched as:

```text
python main.py
```

from:

```text
/Users/madhuram/tradebot-feed-freshness-recovery-v1
```

That direct launch bypassed `run_live.sh`. During that process, both mode environment variables were absent:

```text
TRADING_MODE: unset
EXECUTION_MODE: unset
```

`config/config.py` resolves mode as:

```text
_EXEC_MODE_DEFAULT = os.getenv("EXECUTION_MODE", "SIM")
TRADING_MODE = os.getenv("TRADING_MODE", _EXEC_MODE_DEFAULT)
EXECUTION_MODE = TRADING_MODE
```

With both environment variables absent, the configuration selected the fallback default `SIM`. `main.py` then consumed `cfg.EXECUTION_MODE` and printed `[BOOT] exec_mode=SIM`.

This was a fallback default, not an explicit SIM operator selection.

## Precedence Table

| Source | Value | Present? | Precedence | Final effect |
| --- | --- | ---: | ---: | --- |
| CLI argument | No mode CLI exists for `main.py`; `run_live.sh` flags only control auth/login validation | no | 1 | Did not set mode |
| Environment `TRADING_MODE` | unset for direct instrumented `python main.py` | no | 2 | Could not select LIVE |
| Environment `EXECUTION_MODE` | unset for direct instrumented `python main.py` | no | 3 | `_EXEC_MODE_DEFAULT` became `SIM` |
| Configuration | `TRADING_MODE=os.getenv("TRADING_MODE", _EXEC_MODE_DEFAULT)` | yes | 4 | selected `SIM` |
| Default | hard fallback `"SIM"` in `config/config.py` | yes | 5 | selected `SIM` when env was absent |
| Runtime guard | `enforce_runtime_boot_safety(mode=SIM)` | yes | 6 | accepted SIM; did not promote mode |
| Orchestrator depth startup | starts depth WS only for `LIVE` or `PAPER` | yes | 7 | skipped WebSocket construction |

## Direct Answers

1. The exact code that selected `SIM` was `config/config.py` mode resolution, consumed by `main.py`.
2. The causing value was missing `TRADING_MODE` and missing `EXECUTION_MODE`.
3. `SIM` was a fallback default.
4. `--login-only` refreshed the access token and did not persist or alter mode-related runtime state.
5. The instrumented process did not use the same launch command as original PID `70918`; original was `python /Users/madhuram/tradebot/main.py`, while the instrumented run was `python main.py` from the worktree.
6. It did not use the same working directory. It used the same discovered Python executable path, `/opt/anaconda3/bin/python`, for the current shell, but the original process environment was not captured before PID `70918` exited.
7. The market session was considered open in runtime snapshots.
8. Authentication was valid after `run_live.sh --login-only`; the post-login startup passed Kite REST auth, but still selected SIM because mode env was absent.

## Runtime Path Difference

Runtime paths are repo/worktree relative unless explicitly overridden:

```text
.runtime/
runtime/
logs/
```

The initial worktree-local `.runtime` did not contain `.runtime/kite_access_token`, which caused the first direct `python main.py` to fail closed on auth. After `run_live.sh --login-only`, the worktree token existed and matched the main checkout token hash. That fixed auth, but did not fix runtime mode.

The worktree-local runtime path caused the first authentication blocker. It did not cause the SIM mode blocker. The SIM mode blocker came from launching without the LIVE mode environment that `run_live.sh` normally exports.

## Authoritative Campaign Launch

Use this campaign-specific guarded launch:

```bash
cd /Users/madhuram/tradebot-feed-freshness-recovery-v1
RUN_ID=feed_freshness_live_$(date -u +%Y%m%dT%H%M%SZ)
export RUN_ID
bash scripts/run_feed_freshness_instrumented_live.sh 2>&1 | tee "runtime/live_observation/${RUN_ID}.log"
```

The launcher explicitly sets:

```text
TRADING_MODE=LIVE
EXECUTION_MODE=LIVE
TRADEBOT_MODE=LIVE
LIVE_AUDIT_ONLY=1
ALLOW_LIVE_ORDERS=0
AUTO_TRADE=0
AUTO_ORDER=0
MANUAL_APPROVAL=true
MANUAL_APPROVAL_REQUIRED=1
LIVE_TRADING_ENABLED=false
FEED_OBSERVATION_RUN=1
FEED_RECOVERY_OBSERVATION=1
```

It prints a startup contract and aborts before `main.py` if resolved runtime mode is not `LIVE`, authentication is not valid, automatic live trading is not disabled, or another TradeBot process is already running.

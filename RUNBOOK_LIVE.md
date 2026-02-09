# RUNBOOK_LIVE.md

This runbook assumes NSE governance hours 09:00–17:00 IST. All freshness checks use epoch UTC for truth and IST for display.

## 1) Pre-open (T-30 min)
### Readiness gate
Run:
```
python scripts/readiness_gate.py
```
Pass criteria:
- Exit code `0` and `READY` printed.
- No missing Kite auth or stale feed warnings during market hours.

### Kite token check/refresh
Check:
```
python scripts/validate_kite_session.py
```
If invalid, refresh:
```
python scripts/generate_kite_access_token.py --prompt-token --update-env
```

### Start depth WS and confirm health
Start:
```
python scripts/start_depth_ws.py
```
Confirm health:
```
python scripts/feed_health_status.py
python scripts/sla_check.py
```

## 2) Start sequence (T-5 min)
Start live stack:
```
bash scripts/start_live_stack.sh
```

Confirm running:
```
bash scripts/status_live_stack.sh
```
Expected:
- `depth_ws`, `main`, `watchdog` PIDs running.
- `feed_health_status` shows non-stale required feeds.

## 3) Live monitoring (every 30 min)
Run:
```
python scripts/sla_check.py
python scripts/ops_summary.py
python scripts/risk_monitor.py
```
Good state:
- `tick_lag_sec` and `depth_lag_sec` below thresholds during market hours.
- `RiskState` not in `HARD_HALT`.
- No repeated `FEED_STALE` events without `FEED_RECOVER`.

If stale/blocked:
- Confirm WS status: `bash scripts/status_live_stack.sh`.
- Restart depth WS: `python scripts/start_depth_ws.py`.
- If still stale, stop the stack and investigate auth/WS errors.

## 4) Incident playbooks
### SEV1: hard halt, audit chain fail, DB write fail
Actions:
```
python scripts/flatten_positions.py --dry-run
bash scripts/stop_live_stack.sh
python scripts/incident_bundle.py --incident-id <ID>
```

### SEV2: feed stale / optional cross-asset stale
Actions:
```
python scripts/start_depth_ws.py
python scripts/feed_health_status.py
```

If still stale:
```
bash scripts/stop_live_stack.sh
```

## 5) End-of-day
Reconcile and audit:
```
python scripts/reconcile_fills.py
python scripts/run_daily_audit.py
python scripts/dr_backup.py
python scripts/export_trade_log_csv.py
```
Archive logs:
```
python scripts/daily_rollup.py
```

## 6) Rollback procedures
Flags:
```
python scripts/rollback_flags.py
```
Models:
```
python scripts/rollback_model.py --family xgb --to previous
```
Risk halt reset (only after investigation):
```
python scripts/reset_risk_halt.py
```

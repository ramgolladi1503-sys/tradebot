# Stabilization Runbook

## Safe Run Modes
- Paper: `EXECUTION_MODE=PAPER` and `LIVE_PILOT_MODE=false`
- Pilot: `EXECUTION_MODE=LIVE` and `LIVE_PILOT_MODE=true` with whitelist
- Live: `EXECUTION_MODE=LIVE` with checklist pass and audit green

## Single Command Gate
- `python scripts/regression_gate_stable.py`
- Fails fast on compile, tests, SLA, pilot checklist, audit chain, stress tests.

## Common Failures
- `epoch_missing`: timestamp_epoch not populated in ticks/depth/decisions.
  - Run `python scripts/migrate_timestamps.py` and ensure feeds are live.
- `cross_asset_required_missing`: required feed not supported or stale.
  - Check `python scripts/cross_asset_status.py` and config required feeds.
- `missing_contract`: trade lacks strike/expiry/type.
  - Ensure option chain includes expiry/strike or block trade generation.

## Safe Start
1. `python scripts/sla_check.py`
2. `python scripts/run_pilot_checklist.py --dry-run`
3. `python scripts/regression_gate_stable.py`
4. Start services only after gate passes.

# HTF_RANGE_EXPANSION Real-Paper Operations Runbook

This manual outlines the exact daily operations required to monitor the locked `HTF_RANGE_EXPANSION` candidate in its real-paper observation phase.

## 1. Daily Checklist (09:00 IST)

### Pre-Market Setup
- [ ] Verify environment variables are securely loaded (e.g., `KITE_API_KEY`, `KITE_ACCESS_TOKEN`).
- [ ] Execute token validation script to ensure live tick data access is active.
- [ ] Ensure the server clock is synced to IST via NTP.

### Start Command
To initiate the live observation daemon:
```bash
nohup python scripts/run_htf_real_paper_monitor.py > logs/paper_monitor.log 2>&1 &
```

## 2. Intraday Operations
- **Passive Observation Only**: The daemon evaluates mathematical structure but does not emit live execution payloads.
- **Health Checks**: 
  - Validate `daemon_health.json` is updating dynamically.
  - Command: `cat runtime/daemon_health.json | jq .`
- **Signal Logging**: All state-change vectors are permanently recorded to `runtime/real_paper_signal_log.csv`. Do not manually edit this file while the daemon is running.

## 3. End of Day (15:30 IST)

### Stop Command
Gracefully terminate the paper daemon to prevent off-hours erratic logging:
```bash
pkill -f run_htf_real_paper_monitor.py
```

### Archive Command
Archive the daily log:
```bash
cp runtime/real_paper_signal_log.csv archives/paper/signal_log_$(date +%F).csv
```

### Generating the Summary Report
At the end of every week (or end of day for rapid audits), generate the mathematical tracking summary:
```bash
python scripts/generate_htf_paper_summary.py
```
This automatically outputs the dashboard to the console and generates `runtime/candidate_audits/weekly_paper_report.md`.

## 4. Operational Guardrails
- **DO NOT** execute any live orders via the dashboard.
- **DO NOT** restart the daemon with modified parameter overrides. It handles restart-safety natively by reading open states from the CSV.
- **DO NOT** manually modify `HTF_RANGE_EXPANSION` logic in the codebase based on paper-losses. The strategy is legally locked in `docs/research/htf_range_expansion_strategy_spec.md`.

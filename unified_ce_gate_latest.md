# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `13`
- total_findings: `14`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `0` | `0` |  |
| `cerberus` | `PASS` | `0` | `13` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `changed_paths.txt`
- `core/auth.py`
- `core/decision_dag.py`
- `core/kite_depth_ws.py`
- `core/market_data.py`
- `core/orchestrator.py`
- `core/security_guard.py`
- `core/telegram_alerts.py`
- `core/tick_store.py`
- `docs/agent_reviews/PR_584_feed_latency_bottlenecks.md`
- `start_soak.sh`
- `strategies/trade_builder.py`
- `unified_ce_gate_latest.md`

## Minerva Findings

- No findings.

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `changed_paths.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/auth.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/decision_dag.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/kite_depth_ws.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/market_data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/security_guard.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/telegram_alerts.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/tick_store.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR_584_feed_latency_bottlenecks.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `start_soak.sh` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/trade_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/PR_584_feed_latency_bottlenecks.md` | `PASS` | `evidence_contract_satisfied` |

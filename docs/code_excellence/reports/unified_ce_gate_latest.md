# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `11`
- total_findings: `8`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `1` | `0` |  |
| `cerberus` | `PASS` | `0` | `6` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `core/replay_engine.py`
- `docs/agent_reviews/tick_driven_replay_migration.md`
- `docs/code_excellence/reports/unified_ce_gate_latest.md`
- `scripts/run_paper_replay.py`
- `strategies/volatility_trend.py`
- `tests/test_replay_backtest.py`
- `tests/test_tick_level_fill_resolution.py`
- `tools/legacy/multi_strategy_backtest.py`
- `tools/legacy/replay_backtest.py`
- `tools/legacy/replay_backtest_v2.py`
- `tools/legacy/replay_backtest_v3.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/test_tick_level_fill_resolution.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/replay_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/tick_driven_replay_migration.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_paper_replay.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/volatility_trend.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_tick_level_fill_resolution.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/tick_driven_replay_migration.md` | `PASS` | `evidence_contract_satisfied` |

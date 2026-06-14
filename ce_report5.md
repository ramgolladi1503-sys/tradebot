# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `8`
- total_findings: `9`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `1` | `0` |  |
| `cerberus` | `PASS` | `0` | `8` | `0` |  |
| `evidence` | `PASS` | `0` | `0` | `0` |  |

## Changed Paths

- `core/backtest_elite.py`
- `core/backtest_engine.py`
- `core/option_backtest/models.py`
- `core/option_backtest/report.py`
- `core/tearsheet.py`
- `core/vectorized_signals.py`
- `scripts/run_walk_forward_elite.py`
- `tests/core/test_tearsheet.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/core/test_tearsheet.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/backtest_elite.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/backtest_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/option_backtest/models.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/option_backtest/report.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/tearsheet.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/vectorized_signals.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_walk_forward_elite.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/core/test_tearsheet.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

- No findings.

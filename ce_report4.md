# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `15`
- total_findings: `18`
- total_blocks: `1`
- exit_code: `1`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `BLOCK` | `1` | `2` | `1` |  |
| `cerberus` | `PASS` | `0` | `15` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `core/backtest_elite.py`
- `core/backtest_engine.py`
- `core/option_backtest/adapter.py`
- `core/option_backtest/engine.py`
- `core/option_backtest/models.py`
- `core/option_backtest/report.py`
- `core/tearsheet.py`
- `core/trade_builder_backtest_adapter.py`
- `core/trade_builder_backtest_adapter_v2.py`
- `core/vectorized_signals.py`
- `docs/agent_reviews/real-option-data-backtest-runner-20260614.md`
- `scripts/run_elite_on_real_data.py`
- `scripts/run_walk_forward_elite.py`
- `tests/core/test_tearsheet.py`
- `tests/option_backtest/test_loader.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/core/test_tearsheet.py` | `PASS` | `test_reality_accepted` |
| `tests/option_backtest/test_loader.py` | `BLOCK` | `fake_confidence_test_not_valid_proof` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/backtest_elite.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/backtest_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/option_backtest/adapter.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/option_backtest/engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/option_backtest/models.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/option_backtest/report.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/tearsheet.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/trade_builder_backtest_adapter.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/trade_builder_backtest_adapter_v2.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/vectorized_signals.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/real-option-data-backtest-runner-20260614.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_elite_on_real_data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_walk_forward_elite.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/core/test_tearsheet.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/option_backtest/test_loader.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/real-option-data-backtest-runner-20260614.md` | `PASS` | `evidence_contract_satisfied` |

## Failed Gates

- `minerva` failed with exit_code `1`: blocked findings present

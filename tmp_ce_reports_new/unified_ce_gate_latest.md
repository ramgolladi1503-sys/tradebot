# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/home/runner/work/tradebot/tradebot`
- config_path: `/home/runner/work/tradebot/tradebot/.gsd-forensics.yaml`
- changed_paths: `33`
- total_findings: `42`
- total_blocks: `1`
- exit_code: `1`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `BLOCK` | `1` | `9` | `1` |  |
| `cerberus` | `PASS` | `0` | `32` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `changed_files.txt`
- `changed_paths.txt`
- `core/orchestrator.py`
- `core/orchestrator_parts/cycle.py`
- `core/orchestrator_parts/data.py`
- `core/orders/state_machine.py`
- `core/recovery_state_machine.py`
- `core/regime_router.py`
- `docs/agent_reviews/phase3_continuous_architecture_evidence.md`
- `docs/code_excellence/reports/unified_ce_gate_latest.md`
- `output/wfa_oos_results.csv`
- `pr_body.txt`
- `scripts/run_wfa_intraday.py`
- `scripts/run_wfa_yfinance.py`
- `strategies/banknifty_intraday.py`
- `strategies/nifty_intraday.py`
- `strategies/sensex_intraday.py`
- `strategies/zero_hero.py`
- `test_out.txt`
- `tests/core/test_phase3_alpha_decay_streaming.py`
- `tests/test_feed_recovery_simulation.py`
- `tests/test_orchestrator_latency.py`
- `tests/test_orchestrator_reports_finally.py`
- `tests/test_order_lifecycle.py`
- `tests/test_order_state_machine.py`
- `tests/test_recovery_state_machine.py`
- `tests/test_regime_router.py`
- `tests/test_strategy_pure_signals.py`
- `tmp_ce_reports/changed_paths.txt`
- `tmp_ce_reports/unified_agent_elite_latest.md`
- `tmp_ce_reports/unified_ce_gate_latest.md`
- `trade_builder_diff.txt`
- `unified_ce_gate_latest.md`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/core/test_phase3_alpha_decay_streaming.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_recovery_simulation.py` | `PASS` | `test_reality_accepted` |
| `tests/test_orchestrator_latency.py` | `PASS` | `test_reality_accepted` |
| `tests/test_orchestrator_reports_finally.py` | `PASS` | `test_reality_accepted` |
| `tests/test_order_lifecycle.py` | `PASS` | `test_reality_accepted` |
| `tests/test_order_state_machine.py` | `PASS` | `test_reality_accepted` |
| `tests/test_recovery_state_machine.py` | `PASS` | `test_reality_accepted` |
| `tests/test_regime_router.py` | `BLOCK` | `fake_confidence_test_not_valid_proof` |
| `tests/test_strategy_pure_signals.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `changed_files.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `changed_paths.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator_parts/cycle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator_parts/data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orders/state_machine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/recovery_state_machine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/regime_router.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/phase3_continuous_architecture_evidence.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `pr_body.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_wfa_intraday.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_wfa_yfinance.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/banknifty_intraday.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/nifty_intraday.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/sensex_intraday.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/zero_hero.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `test_out.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/core/test_phase3_alpha_decay_streaming.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_recovery_simulation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_orchestrator_latency.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_orchestrator_reports_finally.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_order_lifecycle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_order_state_machine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_recovery_state_machine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_regime_router.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_strategy_pure_signals.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tmp_ce_reports/changed_paths.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `tmp_ce_reports/unified_agent_elite_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `tmp_ce_reports/unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `trade_builder_diff.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/phase3_continuous_architecture_evidence.md` | `PASS` | `evidence_contract_satisfied` |

## Failed Gates

- `minerva` failed with exit_code `1`: blocked findings present

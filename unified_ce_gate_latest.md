# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `17`
- total_findings: `23`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `5` | `0` |  |
| `cerberus` | `PASS` | `0` | `17` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `core/orchestrator.py`
- `core/orchestrator_parts/cycle.py`
- `core/orchestrator_parts/data.py`
- `core/orders/state_machine.py`
- `core/recovery_state_machine.py`
- `core/regime_router.py`
- `docs/agent_reviews/phase3_continuous_architecture_evidence.md`
- `docs/code_excellence/reports/unified_ce_gate_latest.md`
- `strategies/banknifty_intraday.py`
- `strategies/nifty_intraday.py`
- `strategies/sensex_intraday.py`
- `strategies/zero_hero.py`
- `tests/core/test_phase3_alpha_decay_streaming.py`
- `tests/test_feed_recovery_simulation.py`
- `tests/test_orchestrator_latency.py`
- `tests/test_order_state_machine.py`
- `tests/test_recovery_state_machine.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/core/test_phase3_alpha_decay_streaming.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_recovery_simulation.py` | `PASS` | `test_reality_accepted` |
| `tests/test_orchestrator_latency.py` | `PASS` | `test_reality_accepted` |
| `tests/test_order_state_machine.py` | `PASS` | `test_reality_accepted` |
| `tests/test_recovery_state_machine.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/orchestrator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator_parts/cycle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator_parts/data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orders/state_machine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/recovery_state_machine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/regime_router.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/phase3_continuous_architecture_evidence.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/banknifty_intraday.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/nifty_intraday.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/sensex_intraday.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/zero_hero.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/core/test_phase3_alpha_decay_streaming.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_recovery_simulation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_orchestrator_latency.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_order_state_machine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_recovery_state_machine.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/phase3_continuous_architecture_evidence.md` | `PASS` | `evidence_contract_satisfied` |

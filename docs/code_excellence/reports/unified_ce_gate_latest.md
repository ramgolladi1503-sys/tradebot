# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `6`
- total_findings: `9`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `2` | `0` |  |
| `cerberus` | `PASS` | `0` | `6` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `core/execution/alpha_decay.py`
- `docs/agent_reviews/continuous_architecture_phase1.md`
- `docs/code_excellence/reports/unified_ce_gate_latest.md`
- `ml/continuous_regime.py`
- `tests/test_alpha_decay.py`
- `tests/test_continuous_regime.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/test_alpha_decay.py` | `PASS` | `test_reality_accepted` |
| `tests/test_continuous_regime.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/execution/alpha_decay.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/continuous_architecture_phase1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `ml/continuous_regime.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_alpha_decay.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_continuous_regime.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/continuous_architecture_phase1.md` | `PASS` | `evidence_contract_satisfied` |

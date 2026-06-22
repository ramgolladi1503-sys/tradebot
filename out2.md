# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `7`
- total_findings: `8`
- total_blocks: `1`
- exit_code: `1`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `BLOCK` | `1` | `1` | `1` |  |
| `cerberus` | `PASS` | `0` | `7` | `0` |  |
| `evidence` | `PASS` | `0` | `0` | `0` |  |

## Changed Paths

- `core/htf_paper_telemetry.py`
- `core/opportunity_engine.py`
- `core/paper_exit_outcome.py`
- `docs/strategy_research/htf_opening_drive_paper_validation_plan.md`
- `scripts/summarize_htf_opening_drive_paper.py`
- `strategies/trade_builder.py`
- `tests/strategy_truth/test_htf_strategy_truth.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/strategy_truth/test_htf_strategy_truth.py` | `BLOCK` | `fake_confidence_test_not_valid_proof` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/htf_paper_telemetry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/opportunity_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/paper_exit_outcome.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_research/htf_opening_drive_paper_validation_plan.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/summarize_htf_opening_drive_paper.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/trade_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/test_htf_strategy_truth.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

- No findings.

## Failed Gates

- `minerva` failed with exit_code `1`: blocked findings present

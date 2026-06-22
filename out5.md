# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `10`
- total_findings: `12`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `1` | `0` |  |
| `cerberus` | `PASS` | `0` | `10` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `core/htf_paper_telemetry.py`
- `core/opportunity_engine.py`
- `core/paper_exit_outcome.py`
- `docs/agent_reviews/pr_605_htf_opening_drive_paper_telemetry.md`
- `docs/strategy_research/htf_opening_drive_paper_validation_plan.md`
- `scripts/scheduler.py`
- `scripts/summarize_htf_opening_drive_paper.py`
- `scripts/tick_data_collector.py`
- `strategies/trade_builder.py`
- `tests/strategy_truth/test_htf_strategy_truth.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/strategy_truth/test_htf_strategy_truth.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/htf_paper_telemetry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/opportunity_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/paper_exit_outcome.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_605_htf_opening_drive_paper_telemetry.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_research/htf_opening_drive_paper_validation_plan.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/scheduler.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/summarize_htf_opening_drive_paper.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/tick_data_collector.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/trade_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/test_htf_strategy_truth.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/pr_605_htf_opening_drive_paper_telemetry.md` | `PASS` | `evidence_contract_satisfied` |

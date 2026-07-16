# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/.codex/worktrees/tradebot/canonical-strategy-input-truth-repair`
- config_path: `/Users/madhuram/.codex/worktrees/tradebot/canonical-strategy-input-truth-repair/.gsd-forensics.yaml`
- changed_paths: `8`
- total_findings: `14`
- total_blocks: `9`
- exit_code: `1`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `BLOCK` | `1` | `1` | `1` |  |
| `cerberus` | `PASS` | `0` | `5` | `0` |  |
| `evidence` | `BLOCK` | `1` | `8` | `8` |  |

## Changed Paths

- `changed_files.txt`
- `changed_paths.txt`
- `core/market_data.py`
- `core/ohlc_buffer.py`
- `docs/agent_handoffs/canonical-strategy-input-truth-repair-codex.md`
- `docs/agent_reviews/canonical_strategy_input_truth_repair.md`
- `runtime/strategy_validation/regime_timeline.jsonl`
- `tests/core/test_canonical_strategy_input_truth.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/core/test_canonical_strategy_input_truth.py` | `BLOCK` | `fake_confidence_test_not_valid_proof` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/market_data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/ohlc_buffer.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_handoffs/canonical-strategy-input-truth-repair-codex.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/canonical_strategy_input_truth_repair.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/core/test_canonical_strategy_input_truth.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/canonical_strategy_input_truth_repair.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/canonical_strategy_input_truth_repair.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/canonical_strategy_input_truth_repair.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/canonical_strategy_input_truth_repair.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/canonical_strategy_input_truth_repair.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/canonical_strategy_input_truth_repair.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/canonical_strategy_input_truth_repair.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/canonical_strategy_input_truth_repair.md` | `BLOCK` | `required_evidence_field_missing` |

## Failed Gates

- `minerva` failed with exit_code `1`: blocked findings present
- `evidence` failed with exit_code `1`: blocked findings present

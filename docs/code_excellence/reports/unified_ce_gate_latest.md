# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot-all-strategy-option-e2e-recertification-v4`
- config_path: `/Users/madhuram/tradebot-all-strategy-option-e2e-recertification-v4/.gsd-forensics.yaml`
- changed_paths: `21`
- total_findings: `13`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `0` | `0` |  |
| `cerberus` | `PASS` | `0` | `12` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `docs/agent_reviews/ALL_STRATEGY_AUTHORITY_CLOSURE_V1.md`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/__init__.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/aeron7_nifty_f1_authority_review.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/aeron7_nifty_f1_authority_review.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/all_strategy_authority_matrix.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/all_strategy_authority_matrix.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/authority_blocker_ledger.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/authority_blocker_ledger.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/closure.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_family_authority_reviews.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_family_authority_reviews.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_version_authority_decisions.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_version_authority_decisions.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/input_census_integrity.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/input_census_integrity.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_ledger_authority_review.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_ledger_authority_review.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_authority_prioritization.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_authority_prioritization.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/unresolved_source_authority_review.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/unresolved_source_authority_review.json.sha256`

## Minerva Findings

- No findings.

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/ALL_STRATEGY_AUTHORITY_CLOSURE_V1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/aeron7_nifty_f1_authority_review.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/all_strategy_authority_matrix.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/authority_blocker_ledger.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/closure.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_family_authority_reviews.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_version_authority_decisions.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/input_census_integrity.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_ledger_authority_review.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_authority_prioritization.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/unresolved_source_authority_review.json` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/ALL_STRATEGY_AUTHORITY_CLOSURE_V1.md` | `PASS` | `evidence_contract_satisfied` |

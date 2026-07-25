# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/home/runner/work/tradebot/tradebot`
- config_path: `/home/runner/work/tradebot/tradebot/.gsd-forensics.yaml`
- changed_paths: `37`
- total_findings: `30`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `3` | `0` |  |
| `cerberus` | `PASS` | `0` | `26` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `.github/workflows/_temporary_signal_ledger_provenance_evidence.yml`
- `docs/agent_reviews/SIGNAL_LEDGER_PROVENANCE_V1.md`
- `docs/code_excellence/reports/changed_paths.txt`
- `docs/code_excellence/reports/unified_ce_gate_latest.md`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/__init__.py`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/audit.py`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/build_evidence.py`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/external_evidence_manifest.json`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/external_evidence_manifest.json.sha256`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/generate.py`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/git_provenance.py`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/lineage.py`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/lineage_oracle.py`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/oracle/__init__.py`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/provenance_search.py`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/schema.json`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/schema.json.sha256`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/search_policy.py`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_dataset_review.json`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_dataset_review.json.sha256`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_freeze_contamination_review.json`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_freeze_contamination_review.json.sha256`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_implementation_review.json`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_implementation_review.json.sha256`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_ownership_review.json`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_ownership_review.json.sha256`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_parameter_review.json`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_parameter_review.json.sha256`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_provenance_summary.json`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_provenance_summary.json.sha256`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_source_inventory.json`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_source_inventory.json.sha256`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_temporal_split_review.json`
- `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_temporal_split_review.json.sha256`
- `tests/research/option_e2e/test_signal_ledger_provenance_prior_lineage.py`
- `tests/research/option_e2e/test_signal_ledger_provenance_search_scope.py`
- `tests/research/option_e2e/test_signal_ledger_provenance_v1.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/research/option_e2e/test_signal_ledger_provenance_prior_lineage.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_signal_ledger_provenance_search_scope.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_signal_ledger_provenance_v1.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/SIGNAL_LEDGER_PROVENANCE_V1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/changed_paths.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/audit.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/build_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/external_evidence_manifest.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/generate.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/git_provenance.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/lineage.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/lineage_oracle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/oracle/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/provenance_search.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/schema.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/search_policy.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_dataset_review.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_freeze_contamination_review.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_implementation_review.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_ownership_review.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_parameter_review.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_provenance_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_source_inventory.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledger_provenance_v1/signal_ledger_temporal_split_review.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_signal_ledger_provenance_prior_lineage.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_signal_ledger_provenance_search_scope.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_signal_ledger_provenance_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/SIGNAL_LEDGER_PROVENANCE_V1.md` | `PASS` | `evidence_contract_satisfied` |

# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot-authority-ledger-invalidation-integration-v1`
- config_path: `/Users/madhuram/tradebot-authority-ledger-invalidation-integration-v1/.gsd-forensics.yaml`
- changed_paths: `25`
- total_findings: `24`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `3` | `0` |  |
| `cerberus` | `PASS` | `0` | `19` | `0` |  |
| `evidence` | `PASS` | `0` | `2` | `0` |  |

## Changed Paths

- `docs/agent_reviews/ALL_STRATEGY_AUTHORITY_CLOSURE_V1.md`
- `docs/agent_reviews/SIGNAL_LEDGER_INVALIDATION_AUTHORITY_INTEGRATION_V1.md`
- `docs/code_excellence/reports/changed_paths.txt`
- `docs/code_excellence/reports/unified_ce_gate_latest.md`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/__init__.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/authority_closure_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/authority_closure_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/blocker_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/blocker_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/build_external_closure.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/closure.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/compact_publication.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/external_evidence_manifest.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/external_evidence_manifest.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/provenance_evidence.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/schema.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/schema.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_authority.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_ledger_authority_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_ledger_authority_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_authority_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_authority_summary.json.sha256`
- `tests/research/option_e2e/test_all_strategy_authority_closure_v1.py`
- `tests/research/option_e2e/test_authority_compact_publication_v1.py`
- `tests/research/option_e2e/test_authority_signal_ledger_v1.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/research/option_e2e/test_all_strategy_authority_closure_v1.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_authority_compact_publication_v1.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_authority_signal_ledger_v1.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/ALL_STRATEGY_AUTHORITY_CLOSURE_V1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/SIGNAL_LEDGER_INVALIDATION_AUTHORITY_INTEGRATION_V1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/changed_paths.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/authority_closure_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/blocker_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/build_external_closure.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/closure.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/compact_publication.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/external_evidence_manifest.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/provenance_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/schema.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_authority.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_ledger_authority_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_authority_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_all_strategy_authority_closure_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_authority_compact_publication_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_authority_signal_ledger_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/ALL_STRATEGY_AUTHORITY_CLOSURE_V1.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/SIGNAL_LEDGER_INVALIDATION_AUTHORITY_INTEGRATION_V1.md` | `PASS` | `evidence_contract_satisfied` |

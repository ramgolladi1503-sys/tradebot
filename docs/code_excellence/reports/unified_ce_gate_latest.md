# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot-market-event-graph-live-shadow-v1`
- config_path: `/Users/madhuram/tradebot-market-event-graph-live-shadow-v1/.gsd-forensics.yaml`
- changed_paths: `63`
- total_findings: `52`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `4` | `0` |  |
| `cerberus` | `PASS` | `0` | `47` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `config/config.py`
- `core/kite_depth_ws.py`
- `core/market_data.py`
- `core/market_event_graph_live_runtime_bridge.py`
- `core/market_event_graph_live_shadow.py`
- `core/market_event_graph_live_source.py`
- `core/ohlc_buffer.py`
- `docs/agent_reviews/pr748_market_event_graph_live_shadow_v1.md`
- `docs/code_excellence/reports/changed_paths.txt`
- `docs/code_excellence/reports/unified_ce_gate_latest.md`
- `research/market_event_graph_live_shadow_v1/README.md`
- `research/market_event_graph_live_shadow_v1/SHA256SUMS`
- `research/market_event_graph_live_shadow_v1/breadth_event_ledger.jsonl`
- `research/market_event_graph_live_shadow_v1/candidate_stage_trace.jsonl`
- `research/market_event_graph_live_shadow_v1/constituent_universe_manifest.json`
- `research/market_event_graph_live_shadow_v1/daily_summary.md`
- `research/market_event_graph_live_shadow_v1/frozen_runtime_contract.json`
- `research/market_event_graph_live_shadow_v1/graph_state_ledger.jsonl`
- `research/market_event_graph_live_shadow_v1/hypothetical_outcomes.jsonl`
- `research/market_event_graph_live_shadow_v1/independent_audit_report.json`
- `research/market_event_graph_live_shadow_v1/interval_availability.jsonl`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/artifact_manifest_sha256.json`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/breadth_ledger.jsonl`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/candidate_trace.jsonl`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/checkpoint_20260730T050840Z.json`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/command_invocation_and_environment.json`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/exception_reconnect_restart_ledger.jsonl`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/frozen_stage_a_gate_inventory.json`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/graph_ledger.jsonl`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/hypothetical_separation_evidence.json`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/independent_live_audit_report.json`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/live_constituent_universe_manifest.json`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/live_preflight_report.json`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/pre_run_repository_state.json`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/principal_final_verdict.json`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/producer_summary.json`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/quote_ledger.jsonl`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/raw_live_interval_evidence.jsonl`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/stage_a_gate_matrix.json`
- `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/stage_b_preservation_statement.json`
- `research/market_event_graph_live_shadow_v1/live_constituent_subscription_audit.md`
- `research/market_event_graph_live_shadow_v1/live_observation_command.txt`
- `research/market_event_graph_live_shadow_v1/live_source_discovery_report.md`
- `research/market_event_graph_live_shadow_v1/operational_matrix.jsonl`
- `research/market_event_graph_live_shadow_v1/quote_observation_ledger.jsonl`
- `research/market_event_graph_live_shadow_v1/rejection_summary.json`
- `research/market_event_graph_live_shadow_v1/replay_determinism_report.json`
- `research/market_event_graph_live_shadow_v1/reproduction_command.txt`
- `research/market_event_graph_live_shadow_v1/runtime_path_map.md`
- `research/market_event_graph_live_shadow_v1/sample_replay_input.jsonl`
- `research/market_event_graph_live_shadow_v1/sample_universe_manifest.json`
- `research/market_event_graph_live_shadow_v1/stage_a_report.json`
- `research/market_event_graph_live_shadow_v1/stage_b_report.json`
- `runtime/reference/market_event_graph/nifty50_live_universe_9fb8832853c27944.json`
- `runtime/reference/market_event_graph/nifty50_live_universe_reconciliation_9fb8832853c27944.json`
- `runtime/reference/market_event_graph/official_nse/ind_nifty50list_9fb8832853c27944.csv`
- `scripts/audit_market_event_graph_live_source_v1.py`
- `scripts/build_market_event_graph_live_universe_v1.py`
- `scripts/run_market_event_graph_live_shadow_v1.py`
- `tests/test_market_event_graph_live_runtime_bridge.py`
- `tests/test_market_event_graph_live_shadow.py`
- `tests/test_market_event_graph_live_source.py`
- `tests/test_market_event_graph_live_universe_builder.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/test_market_event_graph_live_runtime_bridge.py` | `PASS` | `test_reality_accepted` |
| `tests/test_market_event_graph_live_shadow.py` | `PASS` | `test_reality_accepted` |
| `tests/test_market_event_graph_live_source.py` | `PASS` | `test_reality_accepted` |
| `tests/test_market_event_graph_live_universe_builder.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `config/config.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/kite_depth_ws.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/market_data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/market_event_graph_live_runtime_bridge.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/market_event_graph_live_shadow.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/market_event_graph_live_source.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/ohlc_buffer.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr748_market_event_graph_live_shadow_v1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/changed_paths.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/README.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/constituent_universe_manifest.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/daily_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/frozen_runtime_contract.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/independent_audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/artifact_manifest_sha256.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/checkpoint_20260730T050840Z.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/command_invocation_and_environment.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/frozen_stage_a_gate_inventory.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/hypothetical_separation_evidence.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/independent_live_audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/live_constituent_universe_manifest.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/live_preflight_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/pre_run_repository_state.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/principal_final_verdict.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/producer_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/stage_a_gate_matrix.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/stage_b_preservation_statement.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_constituent_subscription_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_observation_command.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/live_source_discovery_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/rejection_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/replay_determinism_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/reproduction_command.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/runtime_path_map.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/sample_universe_manifest.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/stage_a_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/market_event_graph_live_shadow_v1/stage_b_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/reference/market_event_graph/nifty50_live_universe_9fb8832853c27944.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/reference/market_event_graph/nifty50_live_universe_reconciliation_9fb8832853c27944.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_market_event_graph_live_source_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/build_market_event_graph_live_universe_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_market_event_graph_live_shadow_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_market_event_graph_live_runtime_bridge.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_market_event_graph_live_shadow.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_market_event_graph_live_source.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_market_event_graph_live_universe_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/pr748_market_event_graph_live_shadow_v1.md` | `PASS` | `evidence_contract_satisfied` |

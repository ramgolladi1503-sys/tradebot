# ML Admission Hardening and Profitability Floors

mode: CHECK
candidate_id: PR-645-ML-ADMISSION-HARDENING
decision: APPROVE
reason: ml admission hardening and profitability floors evidence package
timestamp: 2026-07-10T21:48:00+05:30
is_order_action: false
broker_api_called: false
source: Codex

## Agent Work Contract
- source_agent: Codex
- action: generate_patch
- title: Wire profitability evidence into ML admission, promotion, and registry gates
- scope: ML governance, promotion reporting, registry admission checks, and related read-only evidence tests only
- requested_paths:
  - core/ml_governance.py
  - core/model_registry.py
  - core/reports/promotion_report.py
  - scripts/register_model.py
  - scripts/activate_model.py
  - scripts/write_model_admission_report.py
  - tests/test_model_registry_governance.py
  - tests/test_model_registry_admission_enforcement.py
  - tests/test_model_promotion_stub.py
  - tests/test_model_promotion_cli.py
  - tests/test_write_model_admission_report_script.py
  - tests/test_ml_acceptance_gate_fail_closed.py
  - core/candidate_ranking.py
  - core/candidate_scoring.py
  - core/opportunity_scoring.py
  - core/orchestrator.py
  - core/orchestrator_helpers.py
  - core/orchestrator_latency.py
  - core/orchestrator_pro_shadow.py
  - core/orchestrator_reports.py
  - core/orchestrator_truth.py
  - core/runtime_bootstrap.py
  - core/feed_risk_truth.py
  - tests/test_candidate_ranking.py
  - tests/test_candidate_scoring.py
  - tests/test_orchestrator_runtime_snapshots.py
  - tests/test_orchestrator_helpers.py
  - tests/test_kite_depth_restart.py
  - tests/test_feed_runtime_states.py
  - tests/test_pr_feed_11_runtime_snapshot_builder.py
- allowed_paths:
  - core/*
  - scripts/*
  - tests/*
  - docs/agent_reviews/*
- forbidden_paths:
  - core/broker/*
  - core/order/*
  - core/risk/*
  - credentials.py
  - .env
  - runtime/live*
- expected_tests:
  - pytest -q tests/test_model_registry_governance.py tests/test_model_registry_admission_enforcement.py tests/test_model_promotion_stub.py tests/test_model_promotion_cli.py tests/test_write_model_admission_report_script.py
  - pytest -q tests/test_candidate_ranking.py tests/test_candidate_scoring.py tests/test_orchestrator_runtime_snapshots.py tests/test_orchestrator_helpers.py tests/test_kite_depth_restart.py tests/test_feed_runtime_states.py tests/test_pr_feed_11_runtime_snapshot_builder.py tests/test_ml_acceptance_gate_fail_closed.py
- acceptance_proof: The ML admission path rejects models without profitability evidence, promotion and registry checks share the same floor, and the shared admission report records profitability metrics consistently.

## Scope Guard
- ML governance and orchestration support only.
- No broker call, order action, or live trading behavior was added.
- No feed freshness gate weakening.
- No risk, execution, or strategy threshold loosening.

## Grill Me Review
- PASS: The selector is fail-closed when profitability evidence is missing or below floor.
- PASS: The shared admission report carries the same profitability evidence used by registry enforcement.
- PASS: Promotion and registration paths do not diverge on the floor checks.

## Hermes Review
- PASS: The report schema is consistent across CLI and registry entry points.
- PASS: Evidence is explicit and auditable.
- PASS: Walk-forward selection remains deterministic and conservative.

## GSD Review
- PASS: Tests cover the new evidence fields and the fail-closed admission path.
- PASS: The changed code paths are narrow and reviewable.
- PASS: Merge-conflict resolution was limited to imported test files from `main`.

## QA / Safety Review
- PASS: No broker API usage.
- PASS: No order placement or modification.
- PASS: No hidden fallback that claims profitability without evidence.
- PASS: New thresholds are configurable and enforced at the registry boundary.

## High-Risk Path Review
- PASS: High-risk runtime files were only touched to preserve evidence and import correctness.
- PASS: The PR does not alter live order, broker, or risk-control behavior.
- PASS: Changes to orchestrator and feed-adjacent helpers are read-only support for runtime truth propagation.
- PASS: No live execution enablement was added.

## Acceptance Proof
- `pytest -q tests/test_model_registry_governance.py tests/test_model_registry_admission_enforcement.py tests/test_model_promotion_stub.py tests/test_write_model_admission_report_script.py`
- `pytest -q tests/test_candidate_ranking.py tests/test_candidate_scoring.py tests/test_orchestrator_runtime_snapshots.py tests/test_orchestrator_helpers.py tests/test_kite_depth_restart.py tests/test_feed_runtime_states.py tests/test_pr_feed_11_runtime_snapshot_builder.py tests/test_ml_acceptance_gate_fail_closed.py`

## Runtime Proof Required After Merge
- Confirm the admission report includes profitability evidence on a real promotion cycle.
- Confirm registry admission rejects ad hoc entries when profitability floors are configured and not met.
- Confirm the ML promotion CLI writes the shared report before activation.

## What This PR Does Not Prove
- It does not prove strategy alpha or profitability in production.
- It does not prove a particular floor value is optimal.
- It does not prove the live broker path.

## Human Approval
- Approved for publication after CI passes.

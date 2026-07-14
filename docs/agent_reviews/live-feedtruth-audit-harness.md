# Live FeedTruth Audit Harness

## Agent Work Contract
- source_agent: GSD
- action: GENERATE_PATCH
- title: Live FeedTruth Audit Harness
- scope: Read-only audit harness that inspects existing log/runtime evidence for FeedTruth and execution-truth contradictions without changing runtime behavior.
- mode: AUDIT
- candidate_id: feedtruth_audit_harness
- decision: audit_only
- reason: evidence_consistency
- timestamp: 2026-06-05T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: live_console.log, runtime/feed_runtime_latest.json
- requested_paths:
  - core/feed_truth_audit.py
  - scripts/audit_feed_truth_consistency.py
  - tests/test_feed_truth_audit.py
  - docs/agent_reviews/live-feedtruth-audit-harness.md
- allowed_paths:
  - core/feed_truth_audit.py
  - scripts/audit_feed_truth_consistency.py
  - tests/test_feed_truth_audit.py
  - docs/agent_reviews/live-feedtruth-audit-harness.md
- forbidden_paths:
  - core/kite_depth_ws.py
  - core/orchestrator.py
  - core/broker*
  - core/order*
  - strategies/
  - dashboard/
  - config/
  - runtime/live*
  - logs/broker*
  - secrets*
- expected_tests:
  - PYTHONPATH=. pytest -q tests/test_feed_truth_audit.py -vv
  - PYTHONPATH=. pytest -q tests/test_runtime_execution_truth_evidence.py tests/test_feed_runtime_states.py tests/test_kite_depth_restart.py tests/test_kite_depth_ws_stability.py
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr481_changed_paths.txt
- acceptance_proof: Audit CLI and library report unsafe reportable executable contradictions, duplicate blockers, and blocked/runtime inconsistencies without touching runtime behavior.

## Scope Guard
- This PR is read-only evidence tooling only.
- It must not call broker APIs, place orders, change execution gates, or alter strategy/ranking/Phase2 behavior.
- It must fail closed when required evidence is missing in strict mode.

## Grill Me Review
- Read-only audit code can still cause risk if it misclassifies blocked vs executable evidence.
- The audit must treat duplicate blockers and *_OK markers as invalid blocker evidence.
- The CLI must not silently succeed when the required runtime source is missing in strict mode.

## Hermes Review
- The harness consumes existing live log and runtime JSON evidence and produces a deterministic audit report.
- Default mode warns on missing optional evidence when at least one valid source exists.
- Strict mode fails closed on missing required inputs.

## GSD Review
- Changes are limited to evidence parsing, report generation, CLI wiring, tests, and docs.
- No production execution path is modified.

## QA / Safety Review
- The report is read-only.
- `read_only=true`, `append=false`, `is_order_action=false`, `broker_api_called=false`, and `live_order_allowed=false` remain enforced in audit output.
- The audit reports errors for unsafe reportable executable output under blocked FeedTruth states.

## Acceptance Proof
- The audit detects reportable executable output under `DISCONNECTED`, `RECOVERY_BLOCKED`, and `STALE_OPTION_LTP`.
- The audit fails on fallback/recovered executable-looking traces.
- The audit fails on duplicate blockers and `_OK` markers in blocker output.
- The audit warns on quote-health OK while FeedTruth is blocked.
- The CLI writes JSON and Markdown output.

## Runtime Proof Required After Merge
- Run the audit CLI against a known live log and runtime snapshot to verify the report matches the observed contradiction set.
- Confirm the report is read-only and does not alter any runtime artifacts.

## What This PR Does Not Prove
- It does not change FeedTruth, execution truth, ranking, candidate generation, Phase2, broker/order behavior, or latency thresholds.
- It does not prove the live system is healthy; it only audits evidence that already exists.

## Human Approval
- This is safe to review as evidence tooling only.
- No live execution change is introduced.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false

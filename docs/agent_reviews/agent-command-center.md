# Tradebot Agent Command Center

mode: REVIEW
candidate_id: PR-AGENT-COMMAND-CENTER
decision: add_tradebot_agent_command_center
reason: Add deterministic, read-only forensic agents and a command center that explain where the live trading pipeline fails without changing live runtime behavior.
timestamp: 2026-06-06T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/agent-command-center.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (read-only forensic agent framework + deterministic tests + review doc)
title: Tradebot Agent Command Center
scope: add deterministic forensic agent contracts, safe readers, a command center CLI, and read-only analysis reports for live RCA, feed stability, candidate supply, Phase2/ranking truth, edge measurement, and safety regression
requested_paths:
  - core/agents/*
  - scripts/run_tradebot_agent_command_center.py
  - docs/agents/agent_command_center.md
  - docs/agent_reviews/agent-command-center.md
  - tests/test_agent_contracts.py
  - tests/test_agent_readers.py
  - tests/test_live_rca_agent.py
  - tests/test_feed_stability_agent.py
  - tests/test_candidate_supply_agent.py
  - tests/test_phase2_ranking_truth_agent.py
  - tests/test_edge_measurement_agent.py
  - tests/test_safety_regression_gate_agent.py
  - tests/test_agent_command_center.py
allowed_paths:
  - core/agents/*
  - scripts/run_tradebot_agent_command_center.py
  - docs/agents/*
  - docs/agent_reviews/*
  - tests/test_agent_*.py
forbidden_paths:
  - core/kite_depth_ws.py
  - core/orchestrator.py
  - core/runtime_execution_truth.py
  - core/engine_phase2_adapter.py
  - core/review_queue.py
  - strategies/*
  - core/broker*
  - core/order*
  - dashboard/*
  - runtime/live*
  - logs/*
  - any live broker or websocket startup code
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_agent_contracts.py tests/test_agent_readers.py -vv
  - PYTHONPATH=. pytest -q tests/test_live_rca_agent.py tests/test_feed_stability_agent.py tests/test_candidate_supply_agent.py tests/test_phase2_ranking_truth_agent.py tests/test_edge_measurement_agent.py tests/test_safety_regression_gate_agent.py tests/test_agent_command_center.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/agent_command_center_changed_paths.txt
acceptance_proof:
  - every report is read only
  - every report explicitly says broker_api_called=false and is_order_action=false
  - missing evidence does not crash the readers
  - malformed JSONL does not crash the readers
  - root-cause precedence is deterministic
  - the command center writes only report artifacts
  - no live runtime behavior changes are introduced
```

## Scope Guard

- This PR is read-only forensic analysis only.
- It must not alter broker, order, strategy, ranking, Phase2, or websocket behavior.
- It must fail closed and preserve current safety boundaries.

## Grill Me Review

- The agent layer must not become a hidden trading brain.
- It must not invent evidence or silently smooth over missing files.
- It must keep root-cause precedence deterministic and explainable.

## Hermes Review

- Shared contracts and safe readers are the correct foundation for later agent modules.
- The CLI should only orchestrate read-only analyses and write reports.
- The package must stay isolated from runtime mutation paths.

## GSD Review

- The first PR is the shared contract and command-center shell, not a full live-trading system.
- Later PRs can add richer per-agent heuristics once the contract is stable.

## QA / Safety Review

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `no_order_action=true`
- Missing logs do not crash report generation.
- Malformed JSONL does not crash report generation.

## Acceptance Proof

- The command center emits deterministic JSON and Markdown reports.
- The per-agent reports are read-only and include explicit safety flags.
- The first blocker layer is deterministic given the same inputs.
- The output is explainable and does not claim trading edge.

## Safety Constraints

- No broker/order changes.
- No live orders.
- No live mode.
- No websocket start or restart behavior changes.
- No strategy changes.
- No ranking or scoring formula changes.
- No Phase2 decision changes.
- No dashboard/UI changes.
- No stale-feed relaxation.
- No risk gate relaxation.
- No broad refactor.

## Tests Run

- `PYTHONPATH=. pytest -q tests/test_agent_contracts.py tests/test_agent_readers.py -vv`
- `PYTHONPATH=. pytest -q tests/test_live_rca_agent.py tests/test_feed_stability_agent.py tests/test_candidate_supply_agent.py tests/test_phase2_ranking_truth_agent.py tests/test_edge_measurement_agent.py tests/test_safety_regression_gate_agent.py tests/test_agent_command_center.py -vv`

## What Was Not Changed

- Live trading behavior.
- Strategy logic.
- Ranking logic.
- Phase 2 behavior.
- Broker/order paths.
- Websocket reconnect paths.
- Dashboard/UI behavior.

## Remaining Risks

- The first PR is a foundation. Later agent heuristics may need refinement as more evidence patterns are observed.
- The command center is only as good as the log/snapshot evidence it receives.

## Next PR Recommendation

Add richer per-agent heuristics after the contract and readers are stable.

## Runtime Proof Required After Merge

- Run the command-center CLI against real runtime logs and snapshots.
- Confirm the JSON and Markdown summary artifacts are written to the requested output directory.
- Confirm per-agent latest JSON artifacts are written for every selected agent.
- Confirm missing or malformed evidence does not crash the readers.
- Confirm the output remains read-only and no runtime artifacts are written outside the explicit report directory.

## What This PR Does Not Prove

- It does not prove trading edge or profitability.
- It does not prove live market readiness.
- It does not prove broker readiness.
- It does not prove order execution safety beyond the read-only forensic reports.

## Human Approval

Human approval is required before merge.

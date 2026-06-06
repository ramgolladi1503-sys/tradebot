# Tradebot Agent Command Center Live-Run Sidecar

mode: REVIEW
candidate_id: PR-AGENT-COMMAND-CENTER-LIVE-SIDECAR
decision: add_agent_command_center_live_run_sidecar
reason: Wire the existing Agent Command Center into live runs as a read-only sidecar with watch mode, per-run report directories, and a safe wrapper script without changing trading behavior.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/agent-command-center-live-sidecar.md

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (read-only sidecar wiring + deterministic tests + review doc)
title: Agent Command Center Live-Run Sidecar Wiring
scope: add watch mode to the agent command center CLI, add a wrapper that launches the live bot with a read-only sidecar watcher, and document the safe live-run contract
requested_paths:
  - scripts/run_tradebot_agent_command_center.py
  - scripts/run_live_with_agent_command_center.sh
  - docs/agents/live_run_with_agent_command_center.md
  - docs/agent_reviews/agent-command-center-live-sidecar.md
  - tests/test_agent_command_center_watch.py
  - tests/test_agent_live_sidecar_wrapper_contract.py
allowed_paths:
  - scripts/run_tradebot_agent_command_center.py
  - scripts/run_live_with_agent_command_center.sh
  - docs/agents/*
  - docs/agent_reviews/*
  - tests/test_agent_*.py
forbidden_paths:
  - core/broker*
  - core/order*
  - core/risk*
  - strategies/*
  - dashboard/*
  - runtime/live*
  - logs/*
  - any live broker or websocket runtime wiring
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_agent_command_center_watch.py tests/test_agent_live_sidecar_wrapper_contract.py -vv
  - PYTHONPATH=. pytest -q tests/test_agent_contracts.py tests/test_agent_readers.py tests/test_live_rca_agent.py tests/test_feed_stability_agent.py tests/test_candidate_supply_agent.py tests/test_phase2_ranking_truth_agent.py tests/test_edge_measurement_agent.py tests/test_safety_regression_gate_agent.py tests/test_agent_command_center.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/agent_sidecar_changed_paths.txt
acceptance_proof:
  - the CLI can run once or in watch mode without mutating live trading state
  - per-run report directories are created under `.runtime/agent_reports/runs/<run_id>/`
  - latest reports are copied to the root report directory when requested
  - the wrapper only stops the watcher it started
  - missing logs do not crash the sidecar
  - the wrapper script is executable and does not contain dangerous commands
```

## Scope Guard

- This PR is read-only operational wiring only.
- It must not alter broker, order, strategy, ranking, Phase2, risk, or websocket reconnect behavior.
- It must fail closed and preserve current safety boundaries.

## Grill Me Review

- The sidecar must not become a hidden trading control path.
- The wrapper must not kill unrelated processes or delete locks.
- Watch mode must not mutate runtime state when the bot is live.

## Hermes Review

- The command center should stay a read-only observer of runtime evidence.
- The wrapper should keep `run_live.sh` as the primary foreground process.
- Per-run report directories make live investigations reproducible without changing trading logic.

## GSD Review

- Keep the patch narrow: CLI, wrapper, docs, and deterministic tests only.
- Add tests for watch-once, run-id/run-dir routing, latest copying, and dangerous-command absence.

## QA / Safety Review

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `no_order_action=true`
- Missing logs do not crash report generation.
- The sidecar must not call broker APIs or restart live processes.

## Acceptance Proof

- One-shot command-center runs still work.
- `--watch --once` exits cleanly.
- `--run-id` and `--run-dir` create the expected per-run report path.
- Latest report artifacts are copied when requested.
- The wrapper exists, is executable, and references `run_live.sh`.

## Safety Constraints

- No broker/order changes.
- No live orders.
- No live mode changes.
- No websocket reconnect changes.
- No strategy changes.
- No ranking or scoring formula changes.
- No Phase2 decision changes.
- No dashboard/UI changes.
- No stale-feed relaxation.
- No risk gate relaxation.
- No broad refactor.

## Tests Run

- `PYTHONPATH=. pytest -q tests/test_agent_command_center_watch.py tests/test_agent_live_sidecar_wrapper_contract.py -vv`
- `PYTHONPATH=. pytest -q tests/test_agent_contracts.py tests/test_agent_readers.py tests/test_live_rca_agent.py tests/test_feed_stability_agent.py tests/test_candidate_supply_agent.py tests/test_phase2_ranking_truth_agent.py tests/test_edge_measurement_agent.py tests/test_safety_regression_gate_agent.py tests/test_agent_command_center.py -vv`

## What Was Not Changed

- Live trading behavior.
- Strategy logic.
- Ranking logic.
- Phase 2 behavior.
- Broker/order paths.
- Websocket reconnect paths.
- Dashboard/UI behavior.

## Remaining Risks

- The sidecar is only as good as the logs and runtime snapshots it reads.
- Watch mode can create report churn if pointed at a noisy runtime, but it remains read-only.

## Next PR Recommendation

Observe the sidecar against a real live session and refine evidence aggregation only if it misses a blocker layer.

## Runtime Proof Required After Merge

- Run the wrapper alongside a live session and confirm the watcher emits reports without mutating runtime or trading state.
- Confirm Ctrl+C stops only the watcher created by the wrapper and leaves no unrelated processes touched.

## What This PR Does Not Prove

- It does not prove trading edge or profitability.
- It does not change live order behavior.
- It does not change feed or websocket recovery behavior.
- It does not make the bot more profitable; it only makes the live evidence easier to observe safely.

## Human Approval

Human approval required before merge.


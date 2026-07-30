# PR 748 Market Event Graph Live Shadow V1 Agent Review

mode: READ_ONLY_SHADOW_OBSERVATION
candidate_id: market_event_graph_live_shadow_v1_campaign
decision: PROCEED_AS_DRAFT_REPLAY_WIRING_WITH_LIVE_EVIDENCE_BLOCKER
reason: replay validates observation wiring and safety boundaries while Stage A live availability remains insufficient until a full live captured-metadata session is run
timestamp: 2026-07-30T04:25:00Z
is_order_action: false
broker_api_called: false
source: Codex local worktree /Users/madhuram/tradebot-market-event-graph-live-shadow-v1

## Agent Work Contract

source_agent: Codex
action: GENERATE_PATCH
title: Add Stage A/B read-only live shadow observation harness
scope: Observation-only campaign harness, ledgers, reports, independent audit, CLI, and tests for the frozen Market Event Graph strategy.
requested_paths: core/market_event_graph_live_shadow.py, scripts/run_market_event_graph_live_shadow_v1.py, tests/test_market_event_graph_live_shadow.py, research/market_event_graph_live_shadow_v1/
allowed_paths: core/market_event_graph_live_shadow.py, scripts/run_market_event_graph_live_shadow_v1.py, tests/test_market_event_graph_live_shadow.py, research/market_event_graph_live_shadow_v1/, docs/agent_reviews/pr748_market_event_graph_live_shadow_v1.md
forbidden_paths: broker credentials, live broker authority, order placement, execution promotion, risk limits, frozen graph thresholds, option mapping economics, bearish mirror logic
expected_tests: focused Stage A/B tests plus merged graph producer, adapter, and strategy tests
acceptance_proof: local pytest and compileall commands passed; replay artifacts mark Stage A insufficient and Stage B replay wiring pass.

## Scope Guard

This PR adds a read-only captured-metadata harness. It does not fetch live data, call broker APIs, place or cancel orders, change risk gates, change feed freshness gates, tune thresholds, add option-premium economics, implement the bearish mirror, or promote candidates to execution.

## High-Risk Path Review

Changed high-risk-adjacent file: core/market_event_graph_live_shadow.py. The change is an observation module only. It imports frozen constants from core.market_event_graph_contract and delegates graph matching to the existing producer/adapter/strategy. It sets read_only=true, is_order_action=false, broker_api_called=false, and allowed_for_live_execution=false in ledgers/reports and does not import broker/order/risk/config modules.

## Grill Me Review

The main risk is overclaiming. The committed sample replay proves wiring only, not live runtime availability. Stage A is therefore INSUFFICIENT_LIVE_BREADTH_EVIDENCE. A second risk is treating fixture universe data as live universe proof; the manifest is explicitly labeled sample_replay_manifest_not_live_runtime_universe.

## Hermes Review

The design keeps the existing graph implementation authoritative and adds a separate campaign layer for classification, ledgers, replay, and audit. The CLI consumes captured JSONL so operators can run a full live session later without Codex staying active. The independent auditor re-reads emitted ledgers instead of importing the principal interval classifier.

## GSD Review

Implemented files are narrowly scoped. Runtime and strategy behavior are unchanged. The PR creates durable artifacts under research/market_event_graph_live_shadow_v1 and a script command for replay or future live captured-metadata observation.

## QA / Safety Review

Local commands passed:

```bash
pytest -q tests/test_market_event_graph_live_shadow.py tests/test_market_event_graph_breadth_producer.py tests/test_market_event_graph_live_adapter.py tests/test_market_event_graph_reversal.py
python -m compileall -q core/market_event_graph_live_shadow.py scripts/run_market_event_graph_live_shadow_v1.py
```

Safety assertions covered include partial interval rejection, coverage threshold, stale constituent rejection, timestamp alignment, duplicate/non-monotonic rejection, metadata injection, runtime state validity, candidate identity trace, fallback advisory-only, no broker call, no order action, and independent ledger audit.

## Acceptance Proof

Replay artifact summary:

- Stage A verdict: INSUFFICIENT_LIVE_BREADTH_EVIDENCE
- Stage B verdict: PASS_GRAPH_FORWARD_SHADOW_CORRECTNESS
- Independent audit verdict: PASS_STAGE_A_B_INDEPENDENT_AUDIT
- intervals_observed: 1
- accepted_intervals: 1
- completed_graphs: 1
- candidate_stage_rows: 13
- quote_rows: 1
- hypothetical_outcome_rows: 1
- safety_violation: false

## Runtime Proof Required After Merge

Run at least one full live session with captured market metadata:

```bash
python scripts/run_market_event_graph_live_shadow_v1.py --input PATH_TO_LIVE_CAPTURED_METADATA_JSONL --output research/market_event_graph_live_shadow_v1 --mode LIVE
```

Stage A may only pass after at least 60 completed live intervals, at least 90 percent valid synchronized breadth, at least 40 valid constituents per accepted interval, zero future-data violations, zero duplicate accepted intervals, zero session-crossing accepted intervals, zero malformed accepted rows, and deterministic replay identity.

## What This PR Does Not Prove

This PR does not prove live runtime availability, option profitability, independent market-edge certification, production readiness, live eligibility, broker success, or paper/live execution authority. The replay sample is not a substitute for a full trading-session observation.

## Human Approval

Human approval is required before any live runtime wiring, broker/order/risk/config change, execution promotion, threshold change, or claim that Stage A live availability passed.

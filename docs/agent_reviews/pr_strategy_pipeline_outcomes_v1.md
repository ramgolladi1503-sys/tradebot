# Strict Causal Outcomes Pipeline Review

mode: RESEARCH
candidate_id: STRATEGY_PIPELINE_OUTCOMES_V1
decision: DRAFT_REVIEW_REQUIRED
reason: Replace same-timestamp/LTP-prone outcome replay and hard-coded cost assumptions with exact Truth lineage, causal quote execution, explicit bid/ask fills, and hash-pinned cost configuration.
timestamp: 2026-07-22T20:00:00Z
is_order_action: false
broker_api_called: false
source: agent/strategy-pipeline-outcomes-v1

## Agent Work Contract

Implement only the Outcomes-stage repair above draft PRs #700, #701, and #702. Outcomes must consume exactly one signed Truth result manifest plus caller-declared candidate JSONL, option quote-trace JSONL, and cost-config JSON. Every input is SHA-256 verified inside the subprocess. The stage must enforce completed-bar evidence, an execution-eligible timestamp strictly after the signal timestamp, bid/ask-only fills, bounded entry delay, explicit stop/target/time-stop behavior, and a hash-pinned cost model.

## Scope Guard

In scope: strict causal Outcomes adapter, pipeline routing in the canonical outcome replay command, exact candidate/trace/cost arguments, Truth-to-Outcomes lineage, run-scoped stage and result artifacts, and focused tests.

Out of scope: production signal logic, strategy thresholds, live feeds, broker APIs, order actions, risk controls, dashboards, current statutory-rate claims, statistical validation, WFA, holdout conclusions, certification, and Drift.

The legacy standalone outcome replay remains available when pipeline environment variables are absent. Pipeline mode uses only the strict adapter.

## Grill Me Review

- Can the signal-time quote be used as an entry? No. `execution_eligible_at` must be strictly later than `signal_timestamp`, and the first entry quote must be at or after eligibility.
- Can LTP substitute for an executable quote? No. Every trace row requires positive bid and ask; LTP fallback is forbidden.
- Which side of the spread is used? A long entry buys at ask plus configured slippage; exit sells at bid minus configured slippage.
- Can spread be charged twice? No. Spread is embedded in bid/ask execution, and separate spread cost is fixed at zero.
- Can slippage be charged twice? No. Slippage changes the fill prices, and no separate slippage charge is added.
- Can a delayed quote be treated as immediate execution? No. Entry delay is recorded and must remain within the explicit configured limit.
- Can an absent exit quote fabricate a result? No. The affected input row is marked `INSUFFICIENT_TRACE`; zero complete outcomes blocks the stage with a verified diagnostic artifact.
- Are the tax and brokerage rates claimed to be current? No. The stage requires an explicit caller-owned cost configuration with `source_as_of`; this PR validates and hashes the supplied assumptions but does not assert their legal or market freshness.

## Hermes Review

The adapter is research/paper-only and read-only. It does not import a broker client, place or modify an order, change live configuration, alter risk gates, or consume a live feed. Candidate eligibility is historical evidence only. Outputs explicitly deny live execution authority.

## GSD Review

The older replay selected traces from the candidate timestamp, used the first trace as the entry, accepted LTP traces, globally mixed instrument traces, and hard-coded a lot size. The strict pipeline route instead binds one verified Truth result, one exact candidate file, one exact instrument-keyed bid/ask trace, and one exact cost configuration. It produces complete per-candidate causal checks, fills, costs, MFE/MAE on executable bid, gross/net PnL, and a signed stage result.

## QA / Safety Review

Focused local validation:

- `PYTHONPATH=. pytest -q tests/strategy_pipeline/test_pipeline_engine.py tests/strategy_pipeline/test_pipeline_blocked_artifacts.py tests/strategy_pipeline/test_research_registry_stage_adapters.py tests/strategy_pipeline/test_truth_stage_adapter.py tests/strategy_pipeline/test_truth_fail_closed_edges.py tests/strategy_pipeline/test_outcomes_stage_adapter.py` -> `43 passed`.
- Python compilation for the pipeline modules and canonical Outcomes command -> passed.

Outcomes tests prove next-eligible ask entry, bid exit, target resolution, strictly causal timestamps, completed-bar requirement, zero separately added spread/slippage costs, bid/ask requirement, zero-complete blocking with a hash-verified diagnostic, and rejection of an extra undeclared input.

Full repository CI and every parent-stack workflow must pass on immutable heads.

## Acceptance Proof

Acceptance requires all 43 focused tests, Python compilation, direct pipeline command smoke, and all repository workflows to pass. The stage must block on wrong Truth lineage, same/pre-signal execution eligibility, missing bid or ask, crossed markets, duplicate trace timestamps, stale entry quotes beyond the configured delay, missing exit quotes, invalid or incomplete cost configuration, zero complete outcomes, changed input files, and undeclared extra inputs.

## Runtime Proof Required After Merge

Run a disposable Research → Registry → Truth pipeline, then declare a candidate file, bid/ask trace, and cost configuration as exact Outcomes inputs. Confirm that the orchestrator adds the signed Truth manifest automatically. Retain `outcomes.stage.json` and `outcomes.result.json`. Repeat after changing one trace byte and confirm the adapter-runtime input-hash check blocks execution. Confirm that Statistics remains unavailable until it receives this signed Outcomes result.

## What This PR Does Not Prove

This PR does not prove structural edge, future profitability, perfect fill replication, sufficient sample size, statistical significance, negative-control performance, WFA stability, untouched-holdout performance, certification readiness, paper performance, or live performance. It does not repair Statistics, Certification, or Drift.

## Human Approval

Human review is required before merge. This stacked PR grants no paper or live trading authority, performs no automatic merge or deployment, and cannot call a broker or create an order action.

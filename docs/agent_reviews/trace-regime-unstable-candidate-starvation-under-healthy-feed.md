# Trace REGIME_UNSTABLE Candidate Starvation Under Healthy Feed

mode: REVIEW
candidate_id: PR-TRACE-REGIME-UNSTABLE-CANDIDATE-STARVATION-UNDER-HEALTHY-FEED
decision: add_read_only_candidate_starvation_trace
reason: Live evidence after PR #465 shows healthy feed and quote conditions while REGIME_UNSTABLE dominates and candidates still starve before Phase2. This PR adds a read-only starvation trace so the next live run can explain the survivor funnel, regime metrics, and reject reasons without changing trading behavior.
timestamp: 2026-06-03T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/trace-regime-unstable-candidate-starvation-under-healthy-feed.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (evidence-only runtime trace + deterministic tests)
title: Trace REGIME_UNSTABLE candidate starvation under healthy feed
scope: add read-only candidate starvation evidence identifying why raw candidates do not survive to executable candidates while feed/quote health remains good
requested_paths:
  - core/orchestrator.py
  - core/runtime_candidate_starvation_trace.py
  - tests/test_candidate_starvation_trace_evidence.py
  - docs/agent_reviews/trace-regime-unstable-candidate-starvation-under-healthy-feed.md
allowed_paths:
  - core/orchestrator.py
  - core/runtime_candidate_starvation_trace.py
  - tests/test_candidate_starvation_trace_evidence.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - strategies/*
  - config/*
  - dashboard/*
  - run_live.sh
expected_tests:
  - candidate starvation trace unit tests
  - regime / candidate-flow / no-trade evidence tests
  - full pytest suite
  - agent review evidence validator
  - unified CE gates
acceptance_proof:
  - the artifact surfaces regime_entropy, regime_entropy_max, regime_prob_max, regime_prob_min, unstable_reasons, primary_regime, debounce/streak fields, and per-symbol REGIME_UNSTABLE distribution
  - the artifact surfaces raw_candidate_count, post_scan_survivor_count, post_soft_reject_count, post_real_filter_count, post_executable_filter_count, and top reject reasons
  - confidence_raw_gate and iv_z_bounds reject counts are preserved and no_viable_candidates is reported explicitly when present
  - feed/quote truth is present from the same decision cycle and remains healthy in the live scenario
  - flags: read_only=true, append=false, is_order_action=false, broker_api_called=false
```

## Purpose

PR #465 proved the websocket recovery storm and no-trade evidence contract are stable. The next live blocker is candidate starvation under healthy feed, where `REGIME_UNSTABLE` dominates and BANKNIFTY produces raw candidates that still do not survive to executable opportunities. This PR adds a compact, read-only starvation trace so the next live run can explain that funnel without changing strategy or ranking behavior.

## Files Changed

- `/Users/madhuram/tradebot/core/orchestrator.py`
  - Adds evidence-only starvation snapshot collection from the current cycle and writes the new latest trace.
- `/Users/madhuram/tradebot/core/runtime_candidate_starvation_trace.py`
  - Builds the compact starvation trace payload and fans it out to `logs/`, `.runtime/`, and `.runtime/logs/`.
- `/Users/madhuram/tradebot/tests/test_candidate_starvation_trace_evidence.py`
  - Verifies regime metrics, funnel counts, reject reasons, feed/quote truth, safety flags, and writer fanout.
- `/Users/madhuram/tradebot/docs/agent_reviews/trace-regime-unstable-candidate-starvation-under-healthy-feed.md`
  - Records scope, safety review, and runtime-proof expectations.

## High-Risk Path Review

High-risk file changed: `/Users/madhuram/tradebot/core/orchestrator.py`.

Review outcome:
- The change is evidence-only and does not alter broker/order execution, candidate generation, ranking, or Phase2 behavior.
- It captures counts and existing runtime truth that are already produced during the cycle.
- Failures in evidence writing remain non-fatal.

Residual risk:
- If the current-cycle snapshots are incomplete, the trace intentionally leaves fields null/empty rather than inventing values.

## Scope Guard

### In Scope

- Explain why REGIME_UNSTABLE dominates the cycle.
- Capture per-symbol regime metrics:
  - `regime_entropy`
  - `regime_entropy_max`
  - `regime_prob_max`
  - `regime_prob_min`
  - `unstable_reasons`
  - `primary_regime`
  - regime debounce/streak fields
- Capture the candidate survivor funnel:
  - `raw_candidate_count`
  - `post_scan_survivor_count`
  - `post_soft_reject_count`
  - `post_real_filter_count`
  - `post_executable_filter_count`
- Preserve reject reason details for:
  - `confidence_raw_gate`
  - `iv_z_bounds`
  - `no_viable_candidates`
- Preserve feed/quote truth from the same cycle.

### Out of Scope

- Broker/order code
- Strategy formulas and thresholds
- Ranking and Phase2 behavior
- Dashboard/UI work
- Live-order behavior

### Boundary Verification

- [x] No broker calls added
- [x] No order actions added
- [x] No gate bypass added
- [x] No candidate counts are faked
- [x] No strategy behavior changed
- [x] No threshold changes

## Grill Me Review

### Risks Addressed

- The trace records the full funnel instead of collapsing starvation into a generic `unknown`.
- Healthy feed truth is preserved in the same cycle, so regime starvation is not misattributed to feed failure.
- Unknown or missing evidence is left empty/null rather than inferred.

### Verdict

PASS — evidence-only wiring with explicit fail-closed behavior.

## Hermes Review

### Contract / Architecture Check

- [x] Evidence schema is explicit and versioned.
- [x] Writer provenance is included.
- [x] Safety fields are present.
- [x] Regime trace and survivor funnel are both captured.
- [x] Failure path is observable and fail-closed.

### Verdict

PASS

## GSD Review

### Delivery Check

- [x] Tests prove regime metrics and survivor funnel capture.
- [x] Tests prove reject reasons are preserved.
- [x] Tests prove feed/quote truth is included.
- [x] Tests prove the writer fans out to all three locations.
- [x] No runtime behavior outside evidence changed.

### Verdict

PASS

## QA / Safety Review

Non-negotiables reaffirmed:
- No broker/order code touched.
- No live-order behavior changed.
- No feed, indicator, regime, strategy, or ranking gate bypass added.
- No strategy formula or threshold changed.
- No Phase2 behavior changed.

Evidence/runtime safety flags preserved:
- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`

## Acceptance Proof

### Evidence Contract

The artifact includes:
- schema/provenance fields
- safety flags
- per-symbol regime metrics and unstable reasons
- per-symbol funnel counts
- aggregated funnel counts
- `top_reject_reasons`
- `reject_reason_details`
- feed/quote truth from the same cycle

### Commands Run

```bash
PYTHONPATH=. python -m pytest -q tests/test_candidate_starvation_trace_evidence.py
PYTHONPATH=. python -m pytest -q tests -k "regime_unstable or candidate_starvation or candidate_flow or no_trade"
PYTHONPATH=. python -m pytest -q tests
python scripts/validate_agent_review_evidence.py
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file <generated-file>
```

## Runtime Proof Required After Merge

Required next live validation:
- run an observation-only live session during market hours
- inspect:
  - `logs/candidate_starvation_trace_latest.json`
  - `logs/candidate_flow_trace_latest.json`
  - `logs/notrade_reason_truth_latest.json`
  - `logs/feed_runtime_latest.json`
- confirm:
  - `REGIME_UNSTABLE` is explained per symbol
  - BANKNIFTY shows raw candidates but zero executable survivors
  - `confidence_raw_gate` and `iv_z_bounds` remain visible
  - feed/quote truth stays healthy in the same cycle

## What This PR Does Not Prove

- It does not prove the regime thresholds need to change.
- It does not prove the strategy formulas are wrong.
- It does not prove ranking or Phase2 are at fault.
- It does not make candidates executable.

## Human Approval

This PR must remain draft until a human reviews the evidence-only starvation trace and the next live validation output.

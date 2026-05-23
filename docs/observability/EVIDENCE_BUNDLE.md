# Observability Evidence Bundle

Status: PR-OBS-12  
Scope: deterministic evidence generation from existing serialized observability events

## Purpose

PR-OBS-12 makes the observability spine reviewable without opening Grafana.

The bundle converts existing structured observability events into five deterministic JSON reports:

```text
runtime/evidence/observability_summary.json
runtime/evidence/candidate_decision_funnel.json
runtime/evidence/fallback_safety_report.json
runtime/evidence/feed_freshness_report.json
runtime/evidence/latency_breakdown.json
```

The evidence builder is intentionally pure and read-only. It validates supplied event payloads, derives reports, and writes JSON files. It does not start the trading runtime, inspect broker state, alter candidates, change ranking, or weaken risk checks.

## Inputs

Input must be serialized observability events that already satisfy the event schema from PR-OBS-02.

Required event fields include:

```text
event
run_id
cycle_id
trace_id
stage
decision
timestamp
source
```

Candidate events must include `candidate_id`. Blocked, downgraded, rejected, suppressed, or ignored decisions must include `reason`.

## CLI

Build evidence from a JSONL file:

```bash
python scripts/build_observability_evidence.py \
  --input runtime/logs/observability_events.jsonl \
  --output-dir runtime/evidence
```

The CLI reads JSONL and writes the five JSON reports. Empty lines are ignored. Non-object JSON lines fail closed.

## Reports

### observability_summary.json

Answers:

- How many events were observed?
- How many runs, cycles, and candidates appear?
- Which decisions, stages, and reasons occurred?

### candidate_decision_funnel.json

Answers:

- How many candidates appeared?
- Which stages and decisions did each candidate pass through?
- Did any candidate lack a terminal state?

Terminal states include:

```text
ranked
blocked
downgraded
displayed
paper_ready
paper_submitted
ignored
```

### fallback_safety_report.json

Answers:

- How often did fallback data appear?
- Which candidates were affected by fallback?
- Did any fallback record become executable?

The safe expected value is:

```text
fallback_executable_count = 0
```

### feed_freshness_report.json

Answers:

- How many feed freshness events exist?
- How many fresh and stale events were seen?
- What was the max observed feed age?
- Did any stale-feed record become executable?

### latency_breakdown.json

Answers:

- Which stages emitted latency?
- What are min, max, and average latency by stage?

## Determinism

Reports are sorted by stable event keys:

```text
timestamp
run_id
cycle_id
candidate_id
event
stage
```

JSON output is written with sorted keys and stable indentation so agents can diff and review it.

## Safety boundaries

This PR is observability-only.

It must not:

- change runtime behavior
- start live trading
- inspect or call broker APIs
- rescue missing data
- mutate strategy output
- mutate ranking output
- mutate risk checks
- make observability required for Tradebot to run

## Acceptance proof

Run:

```bash
python -m pytest tests/test_observability_evidence_bundle.py
python scripts/validate_agent_review_evidence.py
```

Manual local proof:

```bash
python scripts/build_observability_evidence.py \
  --input runtime/logs/observability_events.jsonl \
  --output-dir runtime/evidence
```

Then verify these files exist:

```text
runtime/evidence/observability_summary.json
runtime/evidence/candidate_decision_funnel.json
runtime/evidence/fallback_safety_report.json
runtime/evidence/feed_freshness_report.json
runtime/evidence/latency_breakdown.json
```

## What this does not prove

This PR does not prove:

- runtime emits complete event history,
- every candidate has lifecycle events,
- every live run writes evidence automatically,
- fallback safety is enforced by runtime gates,
- feed staleness is solved,
- ranking quality improved,
- paper trading stability improved,
- profitability improved.

It only adds the deterministic evidence bundle builder and writer that later runtime wiring can call.

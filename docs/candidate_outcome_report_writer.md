# Candidate Outcome Report Writer

## Purpose

This module writes deterministic offline JSON and Markdown reports from committed Candidate Outcome fixtures.
It uses the existing fixture loader from PR #485 and the existing Candidate Outcome Truth contract from PR #484.

## Scope

- Closed/off-market environment only.
- Offline report writing only.
- No runtime wiring.
- No broker, order, Kite, websocket, or external service access.

## How It Works

1. Load committed fixtures with the existing fixture loader.
2. Evaluate each fixture with the existing Candidate Outcome Truth contract.
3. Build a deterministic in-memory report.
4. Write a JSON report and a Markdown summary to a caller-provided output directory.

## JSON Report Schema

The JSON report includes:

- `schema_version`
- `generated_by`
- `fixture_count`
- `status_counts`
- `results`
- `safety`

Each result row includes the fixture identity, expected and actual outcome status, summary metrics, and the read-only safety flags.

## Markdown Report Content

The Markdown report includes:

- title
- schema version
- fixture count
- safety flags
- status counts
- result table
- the explicit statement: `This report does not prove trading edge.`

## CLI Usage

```bash
PYTHONPATH=. python scripts/write_candidate_outcome_report.py \
  --fixture-dir tests/fixtures/candidate_outcomes \
  --output-dir /tmp/candidate_outcome_report
```

The default output directory is `docs/code_excellence/reports/candidate_outcomes`.

## Safety Flags

Reports remain read-only and non-action:

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `live_order_action=false`
- `broker_order_action=false`

## What This PR Does Not Do

- It does not wire into runtime.
- It does not aggregate real live outcomes.
- It does not call broker or Kite APIs.
- It does not change strategy, ranking, or execution behavior.
- It does not touch FeedTruth or audit behavior.

## Why This Does Not Prove Trading Edge

The report only formats offline fixture evaluations that are already committed to the repo.
It validates determinism and read-only behavior, not live-market edge or profitability.

## Future PRs

- Outcome aggregation
- Strategy-family summaries
- Regime breakdowns
- Cost/slippage models
- Replay-vs-forward comparison

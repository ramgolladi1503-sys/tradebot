# Opportunity Diagnostics Evidence

PR #56 adds a repeatable evidence-capture wrapper around the PR #55 ranking/opportunity diagnostics.

This is still read-only. It does not build the opportunity engine, change ranking formulas, loosen execution gates, call brokers, submit orders, tune trades, or touch depth subscriptions.

## Why this exists

PR #55 added the diagnostic analyzer. PR #56 makes the analyzer easier to run against either:

1. the latest runtime suggestions file; or
2. an exported JSONL/JSON/CSV sample.

The output is an evidence bundle that can be reviewed before starting candidate-pool or ranking-engine implementation.

## Run against latest runtime logs

```bash
python scripts/capture_opportunity_diagnostics_evidence.py --logs-dir .runtime/logs --print
```

Expected output files:

```text
.runtime/logs/evidence/opportunity_diagnostics_evidence_latest.json
.runtime/logs/evidence/opportunity_diagnostics_evidence_summary.md
```

## Run against an exported file

```bash
python scripts/capture_opportunity_diagnostics_evidence.py --input path/to/suggestions.jsonl --output-dir runtime/evidence --print
```

Supported input formats:

```text
.jsonl
.json
.csv
```

## Evidence interpretation

The evidence bundle records:

- source path and whether the source exists;
- row count;
- confidence distribution;
- flat-confidence detection;
- BUY/SELL side ratios;
- fallback row counts;
- executable / queue-only / advisory counts;
- blocker counts;
- rank-field presence;
- opportunity-score presence;
- whether the visible rows look ranked or merely filtered;
- warnings;
- next recommended action.

## Important limitation

If `.runtime/logs/suggestions.jsonl` is not present in the execution environment, the evidence bundle should be treated as a capture failure, not proof that the bot has no opportunities.

For live truth, run the script on the machine where the bot generated runtime logs.

## Decision rule

Do not start ranking implementation from guesses.

Use the evidence output to decide whether the next PR should be:

- candidate-pool contract;
- rank metadata contract;
- confidence calculation inspection;
- fallback visibility enforcement;
- UI separation between top opportunities and all debug candidates.

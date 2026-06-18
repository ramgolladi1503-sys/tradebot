# Gate Revisit Acceptance Spec

This spec defines how to decide whether a blocked gate should be revisited for threshold relaxation.

## Goal

Increase executable trade count only when blocked candidates show positive forward edge after replay.

## Hard constraints

- Freshness and data-integrity gates stay hard.
- Missing token, stale quote, and chain-availability gates stay hard.
- No live execution behavior changes are allowed here.

## Metrics

For each blocked gate, measure:

- `rejected_count`
- `target_rate`
- `stop_rate`
- `timeout_rate`
- `avg_mfe`
- `avg_mae`
- `avg_best_rr`
- `missed_expectancy`

## Decision rules

- `KEEP_HARD`: target rate is weak and timeouts dominate.
- `KEEP_REVIEW_ONLY`: gate is not clearly overblocking.
- `SAMPLE_ONLY`: gate may deserve a limited shadow-only promotion.
- `REVIEW_FOR_RELAXATION`: gate is a candidate for threshold loosening.

## Promotion policy

- Never relax a safety or freshness gate.
- Only relax alpha filters after replay shows positive edge loss from the block.
- If a gate is relaxed, do it in a staged way:
  - first shadow,
  - then limited size,
  - then full promotion only if live/paper evidence stays positive.

## Run

```bash
PYTHONPATH=. python scripts/run_gate_revisit_report.py --trade-date YYYY-MM-DD --db-path .runtime/db/DEFAULT.sqlite
```

The report writes JSON and Markdown artifacts under the analytics report directory.

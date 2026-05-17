# Ranking and Opportunity Diagnostics

PR #55 is diagnostic-only. It adds a read-only report that inspects emitted candidate/suggestion rows and answers one narrow question:

> Is the UI showing a real ranked opportunity view, or is it only showing emitted rows after filters?

The diagnostic deliberately does **not** change ranking formulas, execution gates, broker calls, order calls, depth subscriptions, or trade tuning.

## Run

```bash
python scripts/diagnose_opportunities.py --logs-dir .runtime/logs
```

Optional export input:

```bash
python scripts/diagnose_opportunities.py --input path/to/export.csv --print
```

Default output:

```text
.runtime/logs/opportunity_diagnostics_latest.json
```

## Report fields

- `row_count` — inspected rows.
- `confidence_raw_min/max/mean/std` — confidence distribution from known confidence fields.
- `flat_confidence_detected` — true when confidence is too clustered to explain real opportunity separation.
- `buy_side_ratio` / `sell_side_ratio` — side bias check.
- `fallback_source_counts` / `recovered_fallback_count` — fallback-heavy output check.
- `executable_count`, `queue_only_count`, `advisory_count` — visible permission/status buckets.
- `top_blocker_counts` — top blockers from emitted rows.
- `rank_field_present` — whether a rank-like field exists.
- `opportunity_score_present` — whether an opportunity-score-like field exists.
- `ui_is_ranked_opportunity_view` — `true`, `false`, or `null` when inconclusive.
- `warnings` — concrete diagnostic warnings to drive the next PR.

## Interpretation

A healthy future opportunity engine should have a real candidate pool, ranking score, rank metadata, side diversity when market context supports it, and clear separation between executable, near-executable, and advisory rows.

A bad report is not a reason to loosen gates. It means the next work should build the candidate-pool/ranking layer with evidence instead of guessing.

## Hard boundaries

Fallback rows are diagnostic evidence only. This PR does not make fallback executable truth.

Do not use this report to tune thresholds blindly. Use it to decide what the next implementation PR must prove.

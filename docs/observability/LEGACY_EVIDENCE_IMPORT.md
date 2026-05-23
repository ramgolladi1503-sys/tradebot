# Legacy Evidence Import

## Purpose

`import_legacy_observability.py` converts old preserved Tradebot logs, CSV snapshots, JSONL rows, or pasted text evidence into observability-compatible JSONL.

This exists because some useful evidence was saved before the newer observability fields existed.

## Honesty rule

Imported rows are partial evidence. They are not full runtime traces.

Every imported event includes:

```text
legacy_import: true
inferred: true
replay_quality: partial
```

This prevents old evidence from being mistaken for complete runtime telemetry.

## Commands

CSV input:

```bash
python scripts/import_legacy_observability.py \
  --input runtime/evidence/legacy_snapshot.csv \
  --output runtime/evidence/legacy_observability_events.jsonl \
  --batch-id ui_snapshot_20260521
```

Text input:

```bash
python scripts/import_legacy_observability.py \
  --input runtime/evidence/legacy_logs.txt \
  --output runtime/evidence/legacy_observability_events.jsonl \
  --format text \
  --batch-id old_logs
```

Replay the converted evidence:

```bash
python scripts/replay_trace.py \
  --input runtime/evidence/legacy_observability_events.jsonl \
  --candidate-id legacy_ui_snapshot_20260521_NIFTY_22500_CE_BUY_1
```

## Supported inputs

```text
csv
jsonl
text key=value lines
```

Useful legacy columns include:

```text
timestamp
symbol
side
status
decision
confidence_raw
score
fallback_state
feed_state
reason
candidate_id
trace_id
cycle_id
run_id
```

Missing IDs are generated deterministically from row content and batch ID.

## What this can prove

```text
What was shown in old evidence.
Whether fallback markers were visible.
Whether stale-feed markers were visible.
Whether confidence looked flat.
Whether old rows can be replayed as partial evidence.
```

## What this cannot prove

```text
Exact strategy path before the row was emitted.
Exact scoring formula path before the row was emitted.
Rejected candidates that never appeared in preserved evidence.
Complete runtime decision lineage.
```

## Acceptance proof

```bash
python -m pytest tests/test_import_legacy_observability.py
```

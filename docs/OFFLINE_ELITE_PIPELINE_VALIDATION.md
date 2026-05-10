# Offline Elite Pipeline Validation Guide

## Purpose

This guide validates the elite pipeline before live market open.

It runs the guard flow offline using fixtures or existing JSON logs.

No broker.
No live feed.
No orders.
No queue mutation.
No main merge.

---

## Pipeline Covered

```text
raw candidate/log row
    ↓
fallback lineage stamping
    ↓
canonical candidate pool
    ↓
review data-truth guard
    ↓
candidate finalization guard
    ↓
guarded risk evaluation
    ↓
capital allocation guard
    ↓
offline summary report
```

---

## Command

Run with default fixture/log discovery:

```bash
python scripts/offline_elite_pipeline_validate.py \
  --out-json logs/offline_elite_pipeline_report.json \
  --out-md logs/offline_elite_pipeline_report.md \
  --fail-on-dirty-capital \
  --print-summary
```

Run with explicit files:

```bash
python scripts/offline_elite_pipeline_validate.py \
  --inputs tests/fixtures/candidates_truth_sample.json logs/review_queue.json \
  --out-json logs/offline_elite_pipeline_report.json \
  --out-md logs/offline_elite_pipeline_report.md \
  --fail-on-dirty-capital \
  --print-summary
```

---

## Test Gate

Run focused tests:

```bash
pytest -q \
  tests/test_data_quality.py \
  tests/test_candidate_pool.py \
  tests/test_shadow_truth.py \
  tests/test_guard_mode_wiring.py \
  tests/test_risk_data_guard.py \
  tests/test_guarded_risk_engine.py \
  tests/test_guarded_review.py \
  tests/test_lineage_stamp.py \
  tests/test_offline_elite_pipeline_validate.py
```

---

## Pass Criteria

Offline validation passes if:

```text
dirty_capital_violations = 0
```

And:

```text
clean candidate can pass pipeline
dirty candidate is blocked by data truth/risk/review/allocation
fallback candidate gets zero capital
unknown quote candidate gets zero capital
stale/missing bid-ask candidate gets zero capital
```

---

## Fail Criteria

Offline validation fails if:

```text
dirty_capital_violations > 0
```

This means dirty data still reached capital allocation.

Do not live validate until this is fixed.

---

## Report Files

```text
logs/offline_elite_pipeline_report.json
logs/offline_elite_pipeline_report.md
```

Review:

```text
total_candidates
pipeline_passed
data_truth_blocked
risk_blocked
capital_allocated
dirty_capital_violations
```

---

## No-BS Rule

Offline validation is not a replacement for live validation.

It proves the pipeline logic behaves correctly with controlled inputs.

Live validation proves the bot behaves correctly under real market data, feed freshness, quote source behavior, broker constraints, and dashboard state.

Both are required.

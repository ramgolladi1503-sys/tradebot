# Elite Opportunity Engine — Documentation Index

## Start Here

Read in this order:

1. `docs/ELITE_OPPORTUNITY_ENGINE_15_POINT_BIBLE.md`
2. `docs/ELITE_OPPORTUNITY_ENGINE_BIBLE.md`
3. `docs/PREMARKET_TRUTH_VALIDATION_CHECKLIST.md`
4. `docs/ELITE_OPPORTUNITY_ENGINE_930_VALIDATION_RUNBOOK.md`
5. `docs/SHADOW_TRUTH_AUDIT_GUIDE.md`
6. `docs/TRUTH_REPORT_INTERPRETATION_GUIDE.md`

---

## Document Purpose

### 1. `ELITE_OPPORTUNITY_ENGINE_15_POINT_BIBLE.md`

The strict operating charter.

Use this to prevent:

```text
main disturbance
runtime rewiring too early
fake confidence
dirty execution
premature merge
```

---

### 2. `ELITE_OPPORTUNITY_ENGINE_BIBLE.md`

The full consultant-style scope Bible.

Covers:

```text
current codebase assessment
core problem
architecture
data truth contract
candidate pool
shadow mode
acceptance gates
implementation roadmap
file-level plan
```

---

### 3. `PREMARKET_TRUTH_VALIDATION_CHECKLIST.md`

Operational checklist before and during market validation.

Use this before 9:30 AM.

---

### 4. `ELITE_OPPORTUNITY_ENGINE_930_VALIDATION_RUNBOOK.md`

The exact live-market validation runbook.

Use this once Tradebot generates live candidates.

---

### 5. `SHADOW_TRUTH_AUDIT_GUIDE.md`

Explains shadow mode and drift classifications.

Use this to understand:

```text
CURRENT_ALLOWS_SHADOW_BLOCKS
EXECUTION_ALLOWED_SHADOW_BLOCKS
SELECTED_SHADOW_BLOCKS
CURRENT_BLOCKS_SHADOW_ALLOWS
NO_DRIFT
```

---

### 6. `TRUTH_REPORT_INTERPRETATION_GUIDE.md`

Explains how to read candidate/opportunity truth reports.

Use this to interpret:

```text
dirty_selected_or_executable
fallback_candidate_count
data quality grades
blockers
merge blockers
```

---

## Scripts

### Candidate truth report

```bash
python scripts/validate_candidate_truth.py \
  --input logs/review_queue.json \
  --out-json logs/candidate_truth_report.json \
  --out-md logs/candidate_truth_report.md \
  --print-summary
```

### Opportunity truth report

```bash
python scripts/build_opportunity_truth_report.py \
  --out-json logs/opportunity_truth_report.json \
  --out-md logs/opportunity_truth_report.md \
  --print-summary
```

### Shadow truth audit

```bash
python scripts/run_shadow_truth_audit.py \
  --out-json logs/shadow_truth_audit.json \
  --out-md logs/shadow_truth_audit.md \
  --print-summary
```

### Final summary gate

```bash
python scripts/summarize_truth_reports.py --fail-if-blocked
```

---

## Focused Test Command

```bash
pytest -q \
  tests/test_data_quality.py \
  tests/test_candidate_pool.py \
  tests/test_validate_candidate_truth_script.py \
  tests/test_build_opportunity_truth_report_script.py \
  tests/test_shadow_truth.py \
  tests/test_run_shadow_truth_audit_script.py \
  tests/test_summarize_truth_reports.py
```

---

## Hard Rule

```text
This branch enriches and audits Tradebot.
It does not change live runtime behavior until explicitly approved.
```

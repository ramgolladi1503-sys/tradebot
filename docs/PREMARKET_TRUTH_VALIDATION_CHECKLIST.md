# Premarket Truth Validation Checklist

## Scope

This checklist is for non-wired validation only.

It does not change Tradebot runtime behavior.

---

## Branch Safety

Confirm branch:

```bash
git branch --show-current
```

Expected:

```text
feature/elite-opportunity-engine-bible
```

Do not run merge commands.

Do not commit to `main`.

---

## 1. Pre-Test Setup

Install/sync dependencies if needed:

```bash
pip install -r requirements.txt
```

Run focused tests:

```bash
pytest -q \
  tests/test_data_quality.py \
  tests/test_candidate_pool.py \
  tests/test_validate_candidate_truth_script.py \
  tests/test_build_opportunity_truth_report_script.py
```

Expected:

```text
all pass
```

---

## 2. Validate Fixture Behavior

Run single-file validator on fixture:

```bash
python scripts/validate_candidate_truth.py \
  --input tests/fixtures/candidates_truth_sample.json \
  --out-json logs/fixture_candidate_truth_report.json \
  --out-md logs/fixture_candidate_truth_report.md \
  --print-summary
```

Expected:

```text
dirty_selected_or_executable = 1
```

This fixture intentionally contains one dirty selected candidate to prove the validator catches it.

Strict mode should fail intentionally:

```bash
python scripts/validate_candidate_truth.py \
  --input tests/fixtures/candidates_truth_sample.json \
  --out-json logs/fixture_candidate_truth_report.json \
  --out-md logs/fixture_candidate_truth_report.md \
  --fail-on-dirty-selected
```

Expected exit code:

```text
1
```

---

## 3. Run Existing Bot Normally

Use your existing command only.

Examples:

```bash
python main.py
```

or:

```bash
./run_live.sh
```

Do not change bot behavior for this validation.

---

## 4. Run Single-File Truth Report

If `logs/review_queue.json` exists:

```bash
python scripts/validate_candidate_truth.py \
  --input logs/review_queue.json \
  --out-json logs/candidate_truth_report.json \
  --out-md logs/candidate_truth_report.md \
  --print-summary
```

Strict mode:

```bash
python scripts/validate_candidate_truth.py \
  --input logs/review_queue.json \
  --out-json logs/candidate_truth_report.json \
  --out-md logs/candidate_truth_report.md \
  --fail-on-dirty-selected \
  --print-summary
```

---

## 5. Run Multi-Source Truth Report

This reads common files if present:

```bash
python scripts/build_opportunity_truth_report.py \
  --out-json logs/opportunity_truth_report.json \
  --out-md logs/opportunity_truth_report.md \
  --print-summary
```

Strict mode:

```bash
python scripts/build_opportunity_truth_report.py \
  --out-json logs/opportunity_truth_report.json \
  --out-md logs/opportunity_truth_report.md \
  --fail-on-dirty-selected \
  --print-summary
```

---

## 6. Review Required Files

Open:

```text
logs/candidate_truth_report.md
logs/opportunity_truth_report.md
```

Check:

```text
dirty_selected_or_executable
fallback_candidate_count
grade_distribution
top blockers
candidate pool counts
```

---

## 7. Pass Criteria

Validation passes only if:

```text
dirty_selected_or_executable = 0
```

And no selected/executable candidate has:

```text
fallback_spread
fallback_liquidity
unknown_quote_source
stale_quote
missing_bid_ask
dirty_execution_entry_source
dirty_execution_entry_lineage
fallback_execution_entry
```

---

## 8. Fail Criteria

Validation fails if:

```text
dirty_selected_or_executable > 0
```

Do not merge.

Do not wire runtime code.

Capture the dirty candidate evidence and create a regression test.

---

## 9. Evidence To Preserve

Save:

```text
logs/candidate_truth_report.json
logs/candidate_truth_report.md
logs/opportunity_truth_report.json
logs/opportunity_truth_report.md
logs/review_queue.json
logs/quick_review_queue.json
logs/approved_trades.json
```

For each dirty candidate, capture:

```text
trade_id
symbol
final_score
candidate_status
execution_status
permission
final_action
data_quality_grade
execution_truth_blockers
fallback_fields
data_lineage
```

---

## 10. No-BS Decision Rule

If the validator finds dirty selected/executable candidates, that is not a validator failure.

That means the current bot still has a truth gap.

The validator is doing its job.

Correct next move:

```text
write failing regression test
keep runtime untouched
fix on feature branch
validate again
wire only after approval
```

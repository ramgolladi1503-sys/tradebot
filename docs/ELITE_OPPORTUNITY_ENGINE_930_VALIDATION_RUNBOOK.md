# Elite Opportunity Engine — 9:30 AM Market Validation Runbook

## Purpose

This runbook validates the non-wired elite opportunity engine enrichment against live-market outputs without changing Tradebot runtime behavior.

The goal is simple:

```text
Run the existing bot normally.
Collect its existing candidate/review outputs.
Run the standalone truth validator separately.
Confirm whether any selected/executable candidate is dirty.
```

No wiring.
No merge.
No main changes.

---

## Hard Safety Rules

```text
main remains untouched.
feature branch only.
validator must not place orders.
validator must not alter queues.
validator must not modify runtime state.
validator only reads candidate/trade JSON and writes reports.
```

If this runbook exposes dirty executable candidates, that is useful evidence. It is not a reason to panic-merge changes into `main`.

---

## Branch

Use:

```bash
git checkout feature/elite-opportunity-engine-bible
```

Confirm:

```bash
git branch --show-current
```

Expected:

```text
feature/elite-opportunity-engine-bible
```

---

## Pre-Market Checks

Run tests for the new non-wired modules:

```bash
pytest -q tests/test_data_quality.py tests/test_candidate_pool.py tests/test_validate_candidate_truth_script.py
```

Expected:

```text
all tests pass
```

If these fail, do not use the validator output as a decision source.

---

## 9:30 AM Validation Flow

### Step 1 — Run Existing Tradebot Normally

Use your normal existing command. Examples:

```bash
python main.py
```

or your existing operational script:

```bash
./run_live.sh
```

Do not change execution behavior for this validation.

---

### Step 2 — Let Existing Bot Produce Outputs

Wait until normal runtime files are generated/updated.

Likely files:

```text
logs/review_queue.json
logs/quick_review_queue.json
logs/approved_trades.json
runtime/review_queue.json
runtime/quick_review_queue.json
```

Actual file depends on your current config.

---

### Step 3 — Run Candidate Truth Validator Separately

Example:

```bash
python scripts/validate_candidate_truth.py \
  --input logs/review_queue.json \
  --out-json logs/candidate_truth_report.json \
  --out-md logs/candidate_truth_report.md \
  --print-summary
```

Strict dry-run gate:

```bash
python scripts/validate_candidate_truth.py \
  --input logs/review_queue.json \
  --out-json logs/candidate_truth_report.json \
  --out-md logs/candidate_truth_report.md \
  --fail-on-dirty-selected \
  --print-summary
```

This command only reads existing output and writes reports.

---

## What To Review

Open:

```text
logs/candidate_truth_report.md
logs/candidate_truth_report.json
```

Check:

```text
total_candidates
execution_truth_allowed
execution_truth_blocked
selected_or_executable_hint
dirty_selected_or_executable
fallback_candidate_count
grade_distribution
top blockers
```

---

## Pass Criteria

The validation passes only if:

```text
dirty_selected_or_executable = 0
```

And:

```text
fallback candidates are advisory/rejected/debug only
unknown quote source candidates are not selected/executable
stale quote candidates are not selected/executable
missing bid/ask candidates are not selected/executable
recovered fallback entries are not selected/executable
```

---

## Fail Criteria

The validation fails if any selected/executable candidate has blockers like:

```text
fallback_spread
fallback_liquidity
unknown_quote_source
stale_quote
missing_bid_ask
dirty_execution_entry_source
dirty_execution_entry_lineage
fallback_execution_entry
fallback_spread_pct
```

Failure means:

```text
Do not merge.
Do not wire runtime logic yet.
Collect evidence.
Fix in feature branch.
Retest.
```

---

## Evidence To Save

Save these files after the run:

```text
logs/candidate_truth_report.md
logs/candidate_truth_report.json
logs/review_queue.json
logs/quick_review_queue.json
logs/approved_trades.json
```

If there is a dirty candidate, capture:

```text
trade_id
symbol
candidate_status
execution_status
permission
final_action
final_score
data_quality_grade
execution_truth_blockers
fallback_fields
data_lineage
```

---

## Example Good Result

```json
{
  "dirty_selected_or_executable": 0,
  "execution_truth_allowed": 2,
  "execution_truth_blocked": 8,
  "fallback_candidate_count": 3,
  "selected_or_executable_hint": 2,
  "total_candidates": 10
}
```

This means selected/executable rows are clean, while dirty rows are not selected.

---

## Example Bad Result

```json
{
  "dirty_selected_or_executable": 1,
  "execution_truth_allowed": 2,
  "execution_truth_blocked": 8,
  "fallback_candidate_count": 3,
  "selected_or_executable_hint": 3,
  "total_candidates": 10
}
```

This means at least one dirty candidate is still considered selected/executable by the existing system.

That is exactly the kind of bug this enrichment is meant to expose.

---

## No-BS Interpretation

If the validator catches dirty selected candidates, the bot is not yet elite.

That does not mean the bot is useless.

It means the current runtime still needs controlled integration of data-truth enforcement.

The correct next step after a failed validation is not to rush a merge.

The correct next step is:

```text
1. identify the dirty candidate pattern
2. write a failing regression test
3. add a non-invasive guard or report first
4. only then propose a controlled runtime integration
```

---

## Merge Rule

Do not merge into `main` until:

```text
all new tests pass
candidate truth report is clean
dashboard still works
9:30 AM validation is clean
user explicitly approves merge
```

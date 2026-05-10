# Shadow Truth Audit Guide

## Purpose

Shadow truth audit is the bridge between non-wired reporting and future controlled integration.

It compares:

```text
current Tradebot runtime hints
vs
new standalone data-truth evaluation
```

It does not change runtime behavior.

---

## What Shadow Mode Does

Shadow mode reads candidates/trades and calculates:

```text
shadow_execution_truth_allowed
shadow_data_quality_grade
shadow_blockers
shadow_fallback_fields
shadow_lineage
```

Then it compares those against current runtime hints such as:

```text
selected_for_execution
is_executable
eligible_for_execution
permission = EXECUTE
final_action = EXECUTE
execution_status = executable
```

---

## What Shadow Mode Does Not Do

It does not:

```text
place orders
modify queues
change execution_allowed
change selected_for_execution
change capital_assigned
change dashboard runtime
write approvals
merge code
```

If the shadow report says a candidate is dirty, that is an observation only.

---

## Run Command

Default multi-source run:

```bash
python scripts/run_shadow_truth_audit.py \
  --out-json logs/shadow_truth_audit.json \
  --out-md logs/shadow_truth_audit.md \
  --print-summary
```

Strict dry-run mode:

```bash
python scripts/run_shadow_truth_audit.py \
  --out-json logs/shadow_truth_audit.json \
  --out-md logs/shadow_truth_audit.md \
  --fail-on-critical \
  --print-summary
```

Specific input files:

```bash
python scripts/run_shadow_truth_audit.py \
  --inputs logs/review_queue.json logs/approved_trades.json \
  --out-json logs/shadow_truth_audit.json \
  --out-md logs/shadow_truth_audit.md \
  --print-summary
```

---

## Drift Types

### NO_DRIFT

Current runtime and shadow truth agree enough.

Action:

```text
observe
```

---

### CURRENT_ALLOWS_SHADOW_BLOCKS

Current runtime hints say the candidate is selected/executable, but shadow truth blocks it.

Severity:

```text
CRITICAL
```

Action:

```text
investigate_before_execution
```

This is the most important drift.

---

### EXECUTION_ALLOWED_SHADOW_BLOCKS

Current `execution_allowed` is true, but shadow truth blocks the candidate.

Severity:

```text
HIGH
```

Action:

```text
downgrade_or_block_before_wiring
```

---

### SELECTED_SHADOW_BLOCKS

Current `selected_for_execution` is true, but shadow truth blocks the candidate.

Severity:

```text
CRITICAL
```

Action:

```text
remove_from_execution_selection
```

---

### CURRENT_BLOCKS_SHADOW_ALLOWS

Current runtime blocks a candidate, but shadow truth thinks the candidate data is clean.

Severity:

```text
LOW
```

Action:

```text
observe_possible_false_negative
```

Do not treat this as a reason to loosen gates immediately.

---

## Pass Criteria

Shadow audit passes if:

```text
CRITICAL = 0
HIGH = 0
```

Strictest possible pass:

```text
CURRENT_ALLOWS_SHADOW_BLOCKS = 0
SELECTED_SHADOW_BLOCKS = 0
EXECUTION_ALLOWED_SHADOW_BLOCKS = 0
```

---

## Fail Criteria

Shadow audit fails if:

```text
CRITICAL > 0
```

It should be treated as a hard signal that current runtime may be allowing dirty candidates.

---

## What To Do On Failure

Do not wire immediately.

Do this:

```text
1. identify dirty candidate trade_id
2. capture blockers and lineage
3. add a fixture/regression case
4. run validator again
5. only then propose guarded runtime integration
```

---

## Evidence To Save

```text
logs/shadow_truth_audit.json
logs/shadow_truth_audit.md
logs/opportunity_truth_report.json
logs/opportunity_truth_report.md
logs/candidate_truth_report.json
logs/candidate_truth_report.md
```

For every critical drift, save:

```text
ref
symbol
current_selected_or_executable
current_execution_allowed
current_selected_for_execution
shadow_execution_truth_allowed
shadow_data_quality_grade
shadow_blockers
shadow_fallback_fields
shadow_lineage
drift_type
drift_severity
recommended_action
```

---

## No-BS Rule

Shadow mode is not a decoration.

If it shows critical drift, the bot is not ready for elite runtime wiring.

If it shows zero critical/high drift across real 9:30 AM data, then controlled guard-mode wiring can be discussed.

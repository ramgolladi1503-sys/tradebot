# Truth Report Interpretation Guide

## Purpose

The truth reports are non-wired audit artifacts.

They do not decide trades.
They do not change queues.
They do not place orders.
They expose whether current Tradebot outputs are clean enough to trust.

---

## Main Report Files

Single-input report:

```text
logs/candidate_truth_report.json
logs/candidate_truth_report.md
```

Multi-source report:

```text
logs/opportunity_truth_report.json
logs/opportunity_truth_report.md
```

---

## The One Metric That Matters First

```text
dirty_selected_or_executable
```

Interpretation:

```text
0 = good; no dirty selected/executable candidates detected
>0 = bad; at least one candidate looks selected/executable while data truth blocks it
```

If this number is above zero, do not merge and do not wire runtime logic.

---

## Key Summary Fields

### total_candidates

Total candidates loaded from the input file or merged sources.

### execution_truth_allowed

Candidates that pass standalone data-truth checks.

### execution_truth_blocked

Candidates blocked by standalone data-truth checks.

### selected_or_executable_hint

Candidates that appear selected/executable based on existing runtime fields.

Fields considered include:

```text
selected_for_execution
is_executable
eligible_for_execution
permission = EXECUTE
final_action = EXECUTE
execution_status = executable
```

### dirty_selected_or_executable

Candidates that existing runtime hints treat as selected/executable, while standalone truth blocks them.

This is the red-alert field.

### fallback_candidate_count

Candidates with fallback fields detected.

Fallback candidates are not automatically wrong, but they must not be executable.

---

## Data Quality Grades

```text
A = clean live data, execution-grade
B = mostly clean, minor weakness
C = degraded/partial, advisory or near-executable only
D = fallback/recovered/unknown/stale, never executable
F = invalid/missing critical data, reject/debug only
```

Current validator is intentionally conservative.

If it marks something D or F, treat that candidate as unsafe until proven otherwise.

---

## Common Blockers

### fallback_spread

Spread was fallback/defaulted.

This means the bot does not have live trustworthy spread evidence.

Action:

```text
Do not execute.
Check bid/ask source.
Check depth/option-chain freshness.
```

### fallback_liquidity

Liquidity score was fallback/defaulted.

Action:

```text
Do not execute.
Check volume/OI/book validation.
```

### unknown_quote_source

The candidate has no trusted quote source.

Action:

```text
Do not execute.
Fix quote_source lineage.
```

### stale_quote

Quote age is above allowed limit.

Action:

```text
Do not execute.
Check feed freshness.
```

### missing_bid_ask

Bid/ask is missing.

Action:

```text
Do not execute.
LTP-only is display-grade, not execution-grade.
```

### dirty_execution_entry_source

Execution entry came from fallback/recovered/synthetic/unknown source.

Action:

```text
Do not execute.
Execution entry must be live ask/bid/valid retained source.
```

### dirty_contract_lineage

Contract mapping is not exact or not trusted.

Action:

```text
Do not execute.
Check option token resolver and fallback policy.
```

---

## How To Read Dirty Candidate Rows

Example:

```text
FIXTURE-DIRTY-FALLBACK-SPREAD symbol=BANKNIFTY grade=D blockers=fallback_spread, dirty_spread_lineage
```

Interpretation:

```text
The candidate may have high score.
The candidate may look selected by current runtime hints.
But spread truth is fallback-derived.
Therefore it must not receive capital or execution permission.
```

---

## Good Outcome

```json
{
  "dirty_selected_or_executable": 0,
  "fallback_candidate_count": 3,
  "selected_or_executable_hint": 2
}
```

Interpretation:

```text
Fallback candidates exist, but none are selected/executable.
That is acceptable.
```

---

## Bad Outcome

```json
{
  "dirty_selected_or_executable": 1,
  "fallback_candidate_count": 3,
  "selected_or_executable_hint": 3
}
```

Interpretation:

```text
At least one dirty candidate is being treated as selected/executable.
That is a real safety gap.
```

---

## What Not To Do

Do not respond to a dirty report by rushing runtime wiring.

Wrong:

```text
validator found dirty executable → patch live runtime immediately → merge
```

Correct:

```text
validator found dirty executable → capture evidence → write regression test → fix on branch → dry-run again → market validate → approve wiring later
```

---

## Merge Decision

Merge is blocked if:

```text
dirty_selected_or_executable > 0
```

Merge can be considered only if:

```text
all focused tests pass
single-source report is clean
multi-source report is clean
9:30 AM validation is clean
user explicitly approves merge
```

# Elite Opportunity Engine — 15-Point Bible

## Purpose

This is the short, strict operating Bible for the Elite Opportunity Engine work.

It exists to prevent scope drift, accidental runtime disturbance, fake confidence, dirty execution, and premature merge into `main`.

---

# 1. Main Is Untouchable

`main` is protected.

No direct commits.
No direct runtime experiments.
No merge without explicit approval.

All work happens on:

```text
feature/elite-opportunity-engine-bible
```

Hard rule:

```text
If it can disturb the working bot, it does not touch main.
```

---

# 2. Enrichment First, Wiring Later

The first stage is enrichment only.

Allowed:

- standalone modules
- validators
- reports
- fixtures
- tests
- docs
- runbooks
- shadow audits

Not allowed without explicit approval:

- changing execution selection
- changing order flow
- changing capital assignment
- changing review queue behavior
- changing dashboard runtime behavior

---

# 3. Data Truth Comes Before Score

A score is meaningless if the data is dirty.

Correct order:

```text
data truth → candidate class → score → rank → risk → allocation
```

Wrong order:

```text
score → rank → maybe check data later
```

No high score can rescue dirty execution data.

---

# 4. Display Is Not Execution

A candidate can be visible and still unsafe.

Display means:

```text
show it for context
```

Execution means:

```text
capital may be placed behind it
```

Those are different.

Example:

```text
High momentum + missing bid/ask = advisory only
```

---

# 5. Fallback Is Never Execution-Grade

Fallback is useful for visibility and debugging.

Fallback is not proof of tradability.

If an execution-critical field is fallback-derived, the candidate must not receive execution permission or capital.

Execution-critical fields:

```text
option LTP
bid
ask
spread
liquidity score
instrument token
contract mapping
execution entry
quote age
```

---

# 6. Unknown Source Means Unsafe

If quote source, spread source, liquidity source, or execution-entry source is unknown, the candidate is not execution-grade.

Unknown lineage should block execution.

It may still remain visible as advisory/debug.

---

# 7. Candidate Pool Must Separate Truth States

The system must not mix all rows into one vague table.

Canonical streams:

```text
top_executable_candidates
near_executable_candidates
advisory_candidates
rejected_candidates
debug_candidates
```

Executable rows must be clean.

Advisory rows may be useful but must not receive capital.

---

# 8. Shadow Mode Before Guard Mode

Before runtime blocking, use shadow mode.

Shadow mode compares:

```text
current runtime hints
vs
new standalone truth result
```

But it does not change:

```text
execution_allowed
selected_for_execution
capital_assigned
queues
dashboard runtime
orders
```

Shadow mode proves the gap without disturbing the bot.

---

# 9. Dirty Selected Candidate Is a Red Alert

The most important failure is:

```text
current system thinks selected/executable
shadow truth says blocked
```

This is classified as:

```text
CURRENT_ALLOWS_SHADOW_BLOCKS = CRITICAL
SELECTED_SHADOW_BLOCKS = CRITICAL
EXECUTION_ALLOWED_SHADOW_BLOCKS = HIGH
```

Critical/high drift blocks merge.

---

# 10. Capital Requires Clean Truth

Capital allocation must never be based only on score.

Capital requires:

```text
clean data lineage
execution truth allowed
valid entry
fresh quote
verified spread
verified liquidity
valid risk budget
portfolio exposure room
```

Dirty candidate result:

```text
capital_assigned = 0
```

---

# 11. Risk Includes Data Risk

Risk is not only stop loss and RR.

Bad data is risk.

Risk blockers must include:

```text
low_data_quality
fallback_execution_field
unknown_quote_source
stale_execution_quote
spread_unverified
missing_bid_ask
contract_fallback_not_execution_safe
```

A clean chart with dirty data is still unsafe.

---

# 12. Tests Must Prove Anti-Lie Behavior

Tests must prove the bot cannot lie to itself.

Required anti-lie cases:

```text
fallback spread blocks execution
fallback liquidity blocks execution
unknown quote source blocks execution
stale quote blocks execution
missing bid/ask blocks execution
recovered fallback entry blocks execution
high score cannot override dirty data
advisory can rank high but cannot execute
capital cannot go to dirty candidate
shadow critical drift is detected
```

---

# 13. Reports Are Evidence, Not Decoration

The reports must be treated as decision artifacts.

Required reports:

```text
candidate_truth_report
opportunity_truth_report
shadow_truth_audit
truth_report_summary
```

A report is useful only if it answers:

```text
What is dirty?
Why is it dirty?
Was it selected/executable?
What blocker caused it?
Should merge be blocked?
```

---

# 14. 9:30 AM Market Validation Is Mandatory

The branch cannot be considered merge-ready without real market validation.

Validation must prove:

```text
dirty_selected_or_executable = 0
shadow CRITICAL = 0
shadow HIGH = 0
fallback candidates are not executable
unknown-source candidates are not executable
stale/missing bid-ask candidates are not executable
```

If validation fails, do not merge.

Capture evidence, add regression tests, fix on branch, retest.

---

# 15. Merge Only After Proof

Merge is allowed only when all conditions pass:

```text
main untouched until approval
focused tests pass
candidate truth report clean
opportunity truth report clean
shadow truth audit clean
premarket checklist complete
9:30 AM validation clean
dashboard unaffected
user explicitly approves merge
```

Until then, the branch remains an enrichment and validation branch only.

No-BS final rule:

```text
The elite bot is not the bot that shows more trades.
The elite bot is the bot that refuses bad trades faster than a human.
```

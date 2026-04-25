# Tradebot Project Control Manual

## Purpose

This document is the operating manual for managing tradebot engineering work. The goal is to stop random branch sprawl and force every change through a controlled workflow.

The project must be managed as an engineering system, not as a collection of experiments.

## Current Hard Rules

1. `main` is protected by discipline even if GitHub branch protection is not configured.
2. Every meaningful change starts from an issue.
3. Every issue gets exactly one primary branch.
4. Every branch must have a narrow purpose.
5. Every pull request must include scope, risk, tests, rollback, and linked issue.
6. No strategy expansion should be merged while core execution is broken.
7. Stock options work stays frozen until index-options execution readiness is proven.

## Required Workflow

```text
Issue -> Branch -> Patch -> Tests -> PR -> Review -> Merge -> Docs update
```

### Step 1: Create or select an issue

Use issue categories:

- `bug`: broken behavior
- `architecture`: structural change
- `test-gap`: missing regression protection
- `execution-risk`: anything that could create a bad live order
- `data-quality`: feed freshness, stale LTP, missing quotes, bad depth
- `dashboard`: UI or reporting mismatch
- `paper-trading`: simulation and adaptive logic
- `live-readiness`: final checks before real execution

### Step 2: Create a focused branch

Allowed branch prefixes:

```text
fix/<specific-problem>
feat/<specific-feature>
docs/<specific-document>
refactor/<specific-module>
test/<specific-coverage>
analysis/<specific-investigation>
```

Bad branch names:

```text
feature/phase3
fix/final
new-changes
latest-working
```

Good branch names:

```text
fix/no-executable-trades
fix/stale-option-ltp-gating
feat/stock-options-liquid-engine
docs/execution-readiness-runbook
test/gating-readiness-regression
```

## Pull Request Template

Every PR must use this structure:

```markdown
## Linked Issue
Closes #<issue-number>

## Purpose
Explain why this change exists.

## Scope
List files/modules changed.

## What Changed
- Bullet 1
- Bullet 2

## Risk
- Execution risk:
- Data risk:
- Dashboard/reporting risk:

## Tests
Paste exact commands and results.

## Rollback Plan
Explain how to disable or revert safely.

## Notes
Anything not solved in this PR.
```

## Debugging Protocol: No Executable Trades

The top priority is issue #26: `Critical: no executable trades – root cause investigation`.

Do not start with strategy ideas. Start with pipeline truth.

Trace the candidate through these stages:

```text
market data -> signal -> opportunity -> candidate -> gating -> review queue -> final emit -> execution intent
```

At each stage capture:

```text
symbol
underlying
strategy
score
confidence_final
execution_score
liquidity_score
candidate_status
execution_status
readiness
execution_allowed
primary_blocker
rejection_reason
ltp
best_bid
best_ask
spread_pct
quote_age_sec
tradingsymbol
instrument_token
```

## Root Cause Buckets

### 1. Feed Freshness Failure

Symptoms:

```text
quote_age_sec too high
LTP missing
bid/ask missing
spread invalid
```

Likely fix areas:

```text
core/feed.py
core/market_data.py
core/kite_depth_ws.py
core/review_queue.py
```

### 2. Contract Resolution Failure

Symptoms:

```text
tradingsymbol missing
instrument_token missing
contract fallback used
CONTRACT_RESOLUTION_FAILED
```

Likely fix areas:

```text
core/instruments.py
core/contract_resolver.py
core/review_queue.py
```

### 3. Gating Misclassification

Symptoms:

```text
candidate has strong score but readiness is ADVISORY_ONLY
execution_allowed false with weak or missing blocker
READY_NOT_APPROVED when it should be EXECUTABLE
```

Likely fix areas:

```text
core/gating_readiness.py
core/decision_engine.py
core/review_queue.py
```

### 4. Score Mismatch

Symptoms:

```text
opportunity_score high
execution_score low
confidence_final overwritten
normalizer changes persisted values
```

Likely fix areas:

```text
core/opportunity_engine.py
core/decision_engine.py
core/review_queue.py
```

### 5. Liquidity Threshold Too Strict

Symptoms:

```text
spread slightly above threshold
volume or OI thresholds block every candidate
liquidity_score is always below minimum
```

Likely fix areas:

```text
config/config.py
core/decision_engine.py
core/gating_readiness.py
```

## Required Evidence Before Fixing

Before changing code, collect one run with:

```bash
rg -n "FINAL EMIT|candidate_status|execution_status|readiness|primary_blocker|CONTRACT_RESOLUTION|TB_RANKED_COUNT_EXECUTABLE" logs/*.log
```

If logs are in another file:

```bash
rg -n "FINAL EMIT|ADVISORY_ONLY|READY_NOT_APPROVED|EXECUTABLE|primary_blocker|quote_age|spread|tradingsymbol|instrument_token" <log-file>
```

## Stop Rules

Stop and do not merge if any of these are true:

1. Candidate becomes executable with missing token or tradingsymbol.
2. Candidate becomes executable with stale quote.
3. Final confidence is recomputed after persistence.
4. Dashboard says executable but execution layer says blocked.
5. Tests are not added for the bug fixed.

## Immediate Project Priorities

### P0

- Fix issue #26: no executable trades.
- Add trace logging for candidate drop reasons.
- Prove at least one valid executable candidate in controlled conditions.

### P1

- Clean PR #19 stock options subsystem.
- Add PR description, tests, risks, and rollback.
- Rebase or recreate PR if it remains unmergeable.

### P2

- Clean stale branches.
- Keep only branches with active issues or active PRs.

## Branch Cleanup Policy

Keep:

```text
main
backup/main-clean-snapshot
active issue branches
active PR branches
```

Archive or delete later:

```text
tmp-tree-test
older overlapping feature branches
merged phase2 branches
abandoned experiment branches
```

Do not delete branches until their useful commits are compared against `main`.

## Definition of Done

A change is done only when:

1. The linked issue is closed.
2. The PR is merged.
3. Tests passed and are documented.
4. The relevant runbook or project doc is updated.
5. Any new risk has a clear guardrail.

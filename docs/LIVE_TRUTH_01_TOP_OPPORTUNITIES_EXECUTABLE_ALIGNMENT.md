# LIVE-TRUTH-01 — Top Opportunities Executable Truth Alignment

## Purpose

LIVE-TRUTH-01 makes top-opportunities executable truth auditable.

The live evidence showed a dangerous mismatch pattern:

```text
ranked_executable_count > 0
top_reportable_executable = true
top_opportunities_executable_count = 0
```

This PR adds a read-only reducer that compares ranked executable evidence with top-opportunities evidence and reports mismatches explicitly.

It also adds trace-completeness validation for top executable candidate evidence so runtime debugging can see the actual trade-quality fields behind a reported executable candidate.

## Scope

In scope:

- Compare ranked executable count with top-opportunities executable count.
- Compare ranked top-reportable executable truth with top-opportunities top-reportable executable truth.
- Detect missing top executable in top-opportunities evidence.
- Validate full top executable trace completeness.
- Validate runtime candidate handoff completeness.
- Preserve read-only and non-action metadata.

Out of scope:

- Order placement.
- Forced execution.
- Runtime state mutation.
- Broker or adapter calls.
- Dashboard changes.
- Artifact writer behavior changes.
- Latest artifact preservation logic; that belongs to LIVE-TRUTH-02.

## Module

```text
core/live_truth_top_opportunities_alignment.py
```

Main function:

```python
build_top_opportunities_executable_alignment(...)
```

Status values:

- `TOP_OPPORTUNITIES_EXECUTABLE_TRUTH_ALIGNED`
- `TOP_OPPORTUNITIES_EXECUTABLE_TRUTH_BLOCKED`
- `TOP_OPPORTUNITIES_EXECUTABLE_TRUTH_MISMATCH`

Mismatch reasons:

- `executable_count_mismatch`
- `top_reportable_executable_mismatch`
- `top_executable_missing_from_top_opportunities`
- `top_executable_trace_incomplete`
- `runtime_candidate_handoff_incomplete`

## Required top executable trace fields

Every `TB_TOP_EXECUTABLE_CANDIDATE` event and `runtime_candidate_handoff_latest.json` payload must include:

- `trade_id`
- `appeared_at`
- `symbol`
- `strike`
- `option_type`
- `strategy_family`
- `entry`
- `execution_entry`
- `stop_loss`
- `target`
- `risk_reward`
- `rank_score`
- `source_quote_age`
- `bid`
- `ask`
- `ltp`

## Safety behavior

This PR is evidence-only.

It does not:

- place orders
- force execution
- call brokers
- call adapters
- mutate runtime state
- write artifacts
- relax stale-feed or quote-truth protection
- change executable quality gates

## Test proof

Focused tests cover:

- ranked executable truth present while top-opportunities executable count is zero
- aligned executable truth
- deriving counts from candidate lists
- incomplete top executable trace fields
- incomplete runtime candidate handoff fields
- no trace requirement when executable truth is absent
- invalid input blocking
- JSON serialization and non-action metadata

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_live_truth_01_top_opportunities_alignment.py
```

## Next

After LIVE-TRUTH-01 merges green, continue to LIVE-TRUTH-02 — Latest Artifact Non-Empty Preservation.

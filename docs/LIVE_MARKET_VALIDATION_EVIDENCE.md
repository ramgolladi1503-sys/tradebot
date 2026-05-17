# Live Market Validation Evidence Pack

## Purpose

This document defines how to validate Tradebot during live market hours after the feed/staleness/depth cleanup work.

This is not a profitability test.

This is a truth test.

The goal is to prove that the bot can tell the truth about:

```text
feed connection
option subscription health
quote freshness
stale blockers
prune behavior
candidate visibility
executable blockers
```

## Why This Exists

The project now has a stable foundation:

```text
depth ownership checks pass
depth subscription tests pass
stale-prune hysteresis tests pass
full pytest passes
generic full_pytest_contracts shim removed
feed/staleness observability pack added
```

But off-market tests cannot prove live-market feed behavior.

Live validation is required because the failure modes are runtime-specific:

- websocket may connect but stop receiving useful option ticks;
- option token subscriptions may silently shrink;
- stale-prune may be too aggressive or too weak;
- LTP may be fresh for index but stale for options;
- dashboard rows may appear while execution should stay blocked;
- executable count may be zero for valid reasons or broken reasons.

This document prevents fake confidence.

## What This Validation Must Not Do

Do not use this validation to justify real-money trading.

Do not loosen gates to create executable rows.

Do not mark fallback quotes as executable truth.

Do not call broker order APIs.

Do not claim the system is production-ready from one session.

## Required Runtime Duration

Minimum:

```text
15 minutes continuous live runtime
```

Preferred:

```text
30 minutes continuous live runtime
```

Run during active market hours only.

## Required Runtime Files

The validation pack expects these runtime files when available:

```text
feed_runtime_latest.json
runtime_health_latest.json
engine_cycle_status.json
suggestions_status.json
suggestions.jsonl
events.jsonl
feed_staleness_observability_latest.json
```

The paths should resolve through `core.paths.logs_dir()` or explicit `--logs-dir` passed to the validation script.

## Pre-Run Checklist

Before starting the live run:

```bash
git checkout main
git pull

PYTHONPATH=. python scripts/validate_depth_offmarket.py
PYTHONPATH=. pytest -q tests/test_depth_subscription_tokens.py
PYTHONPATH=. pytest -q tests/test_stale_option_prune_hysteresis.py
PYTHONPATH=. pytest -q tests/test_feed_staleness_observability.py
```

Expected:

```text
all checks pass
```

If these fail, do not start live validation.

## Live Run Procedure

Start the bot using the normal live command for the repository.

Let it run continuously for 15 to 30 minutes.

During or after the run, generate the feed/staleness evidence:

```bash
PYTHONPATH=. python scripts/observe_feed_staleness.py
```

To inspect directly:

```bash
PYTHONPATH=. python scripts/observe_feed_staleness.py --print
```

Then generate the live validation evidence report:

```bash
PYTHONPATH=. python scripts/validate_live_market_evidence.py
```

## Pass Conditions

A live validation session is acceptable only if the report can show:

```text
feed_ok is true or clearly explained when degraded
websocket connected state is visible
subscribed_option_tokens_count is visible and not collapsed to zero
stale option/index blockers are visible when present
visible_executable_count is visible
candidate/execution blockers are visible
report marks read_only=true
report marks is_order_action=false
```

## Fail Conditions

The session fails validation if any of these happen:

```text
runtime files are missing without explanation
websocket disconnects and does not recover
option token subscription collapses to zero during market hours
option LTP is stale but executable rows are still allowed
fallback quote truth becomes executable truth
blockers are missing or opaque
feed degraded state is hidden from the report
```

## Evidence Fields to Review

From `feed_staleness_observability_latest.json`:

```text
summary.feed_ok
summary.ws_connected
summary.subscribed_option_tokens_count
summary.visible_executable_count
summary.missing_runtime_files
summary.errored_runtime_files
stale_evidence
blocker_evidence
status_counts
read_only
is_order_action
```

## Evidence Template

Use this section after each live run.

```text
Date:
Market session:
Run duration:
Commit SHA:
Branch:
Broker/feed mode:

feed_ok:
ws_connected:
subscribed_option_tokens_count:
visible_executable_count:

Top stale evidence:
Top blocker evidence:
Status counts:

Did option subscription collapse? yes/no
Did stale data produce executable rows? yes/no
Did fallback quote truth become executable truth? yes/no

Verdict: PASS / FAIL / INCONCLUSIVE
Reason:
Next action:
```

## Interpretation Rules

Zero executable trades is not automatically a failure.

It is acceptable if blockers are truthful:

```text
STALE_OPTION_LTP
WIDE_SPREAD
LOW_CONFIDENCE
UNRESOLVED_CONTRACT
FEED_STALE
PRICE_MISMATCH
```

It is not acceptable if blockers are missing or vague.

The system must explain why it did or did not produce executable rows.

## Next Roadmap Step After This

After live validation evidence exists, the next phase should focus on ranking and opportunity-engine diagnostics.

Do not start ranking optimization until live feed/staleness truth is proven or at least clearly measured.

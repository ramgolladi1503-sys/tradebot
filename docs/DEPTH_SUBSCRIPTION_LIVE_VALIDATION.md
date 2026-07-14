# Depth Subscription Live Validation Checklist

## Purpose

This checklist validates the depth subscription rewrite that landed through PR #39 and the depth compatibility cleanup that landed through PR #40.

The goal is not to force trades. The goal is to prove that the subscription engine keeps the right option universe alive, preserves underlying tokens, avoids stale-prune damage, and gives the trading pipeline enough fresh option LTP/depth data to make honest decisions.

A correct result may still be `NO_TRADE`, `WATCHLIST`, or `BLOCKED`. That is acceptable when the reasons are real: stale feed, weak signal, poor liquidity, unresolved contract, market regime mismatch, or gate failure.

## Scope

Validated behavior:

- `core.depth_subscription_engine` owns final depth subscription behavior.
- Legacy depth compatibility paths do not override the new engine.
- NIFTY, BANKNIFTY, and SENSEX option windows are selected around ATM.
- SENSEX/BFO option tokens are preserved.
- Sticky/current-position tokens are not dropped by budget logic.
- Stale option pruning respects symbol floors.
- Session-tick-required logic does not prune a symbol before the first option tick for that session.
- Refresh delta logic can unsubscribe removed stale tokens and refresh stale symbols.

Out of scope:

- No profitability guarantee.
- No relaxation of execution gates.
- No forced executable trades.
- No live order placement unless execution mode is explicitly configured for live and manually approved.

## Pre-run Requirements

Before running live validation:

- Main branch must contain PR #39 and PR #40.
- Required CI checks must be green:
  - `tests`
  - `ci`
  - `Portfolio CI`
  - `CodeQL Advanced`
- Run in safe/paper mode by default.
- Do not loosen quality gates to create trades.
- Confirm broker token state before market open.
- Confirm runtime directory is writable.

Recommended environment:

```bash
export EXECUTION_MODE=PAPER
export KITE_USE_API=false
export PYTHONPATH=.
```

Use live broker/API flags only when intentionally validating real feed behavior. Do not combine feed validation with live order execution.

## Validation Windows

Minimum useful observation windows:

1. **Startup window:** first 3 to 5 minutes after process start.
2. **Stability window:** 15 to 30 minutes of continuous market run.
3. **Stress window:** one fast-moving period, if available, where ATM shifts or option ticks become uneven.

## Commands

### 1. Confirm branch and latest commit

```bash
git branch --show-current
git log -1 --oneline
```

Expected:

- Branch is `main` or a validation branch based on latest main.
- Latest history includes PR #39 and PR #40 merge commits.

### 2. Run targeted depth tests locally

```bash
PYTHONPATH=. pytest -q tests/test_depth_subscription_tokens.py
```

Expected:

- All depth subscription tests pass.

### 3. Run full CI-equivalent tests locally when time allows

```bash
PYTHONPATH=. pytest -q
```

Expected:

- Full suite passes.

### 4. Start safe runtime validation

Use the project’s normal runtime entrypoint. Default to paper/safe mode:

```bash
EXECUTION_MODE=PAPER KITE_USE_API=false PYTHONPATH=. python main.py
```

If validating real broker feed, explicitly document the chosen flags and confirm that live orders are disabled unless intentionally approved.

## Runtime Files to Inspect

Check these files during and after the run:

```text
.runtime/logs/feed_runtime_latest.json
.runtime/logs/runtime_health_latest.json
.runtime/logs/engine_cycle_status.json
.runtime/logs/suggestions_status.json
.runtime/logs/suggestions.jsonl
.runtime/logs/events.jsonl
```

If the repo writes equivalent paths under `logs/`, record the actual paths used.

## Evidence Checklist

Capture the following evidence.

### Feed Runtime

From `feed_runtime_latest.json`, record:

```text
feed_ok=
ws_connected=
subscribed_tokens_count=
subscribed_option_tokens_count=
option_feed_status_by_symbol=
option_feed_block_reason_by_symbol=
runtime_state=
derived_reasons=
```

Expected:

- `ws_connected=true` during live feed validation.
- Option token count is non-zero for active symbols.
- No repeated subscription collapse to only underlying tokens.
- Any block reason is explicit and explainable.

### Runtime Health

From `runtime_health_latest.json`, record:

```text
sla_status=
feed_blockers=
ltp_age_by_symbol=
option_ltp_age_by_symbol=
```

Expected:

- No persistent unexplained feed degradation.
- If feed is degraded, blockers must name exact stale/missing symbols.

### Engine Cycle

From `engine_cycle_status.json`, record:

```text
current_cycle_candidates_seen=
current_cycle_candidates_enqueued=
visible_suggestion_count=
visible_advisory_count=
visible_queue_only_count=
visible_executable_count=
primary_blocker=
```

Expected:

- `visible_executable_count=0` is acceptable only if blocker reasons are real.
- No false `NO_CANDIDATES` when visible suggestions exist.

### Suggestions

From `suggestions.jsonl` or `suggestions_status.json`, record for top rows:

```text
symbol=
tradingsymbol=
instrument_token=
entry=
stop_loss=
target=
confidence=
liquidity=
data_freshness=
execution_status=
permission=
primary_blocker=
block_reasons=
```

Expected:

- Real candidates must have contract identity when they are execution eligible.
- No row should become executable if contract, quote, or feed freshness is broken.
- Synthetic/fallback rows must remain advisory/blocked.

## Pass Criteria

The depth rewrite passes live validation when all of these are true:

- Process starts without import-hook conflict or depth patch fighting.
- Depth subscriptions include underlying plus option tokens for expected symbols.
- NIFTY, BANKNIFTY, and SENSEX retain expected option coverage when enabled.
- SENSEX/BFO tokens are not dropped by validation/budget logic.
- Sticky/current-position tokens are preserved.
- Stale pruning does not reduce a symbol below the configured floor.
- No symbol is pruned before first session option tick when session-tick guard is enabled.
- Refresh delta can remove stale/unwanted tokens without collapsing the whole universe.
- Feed/runtime logs explain every blocker.
- Full CI remains green after any follow-up fixes.

## Fail Conditions

Stop and investigate if any of these occur:

- `subscribed_option_tokens_count=0` during market hours for enabled option symbols.
- Underlying tokens are present but option tokens disappear after refresh.
- SENSEX option tokens disappear while NIFTY/BANKNIFTY remain present.
- Stale-prune metadata reports protected/pruned counts that do not match final tokens.
- `visible_executable_count=0` with no clear blocker reason.
- Runtime health reports persistent stale option LTP for all symbols despite active subscriptions.
- Any import-hook compatibility module overrides `core.depth_subscription_engine` behavior again.

## Evidence Template

Fill this after the live run.

```text
Date:
Market session:
Branch/commit:
Execution mode:
Feed mode:
Run duration:

CI before run:
- tests:
- ci:
- Portfolio CI:
- CodeQL Advanced:

Startup evidence:
- feed_ok:
- ws_connected:
- subscribed_tokens_count:
- subscribed_option_tokens_count:
- symbols covered:

15-30 minute stability evidence:
- feed blockers:
- stale symbols:
- option token count min/max:
- refresh events observed:
- stale prune events observed:

Candidate evidence:
- visible_suggestion_count:
- visible_executable_count:
- primary blocker:
- top 3 candidate statuses:

Decision:
PASS / FAIL / NEEDS FOLLOW-UP

Follow-up issue/PR needed:
Notes:
```

## Interpretation Rules

Do not treat lack of trades as failure. Treat lack of truthful reason as failure.

Examples:

- Good `NO_TRADE`: `FEED_STALE`, `LOW_CONFIDENCE`, `UNRESOLVED_CONTRACT`, `LIQUIDITY_WEAK`.
- Bad `NO_TRADE`: empty reason, miss-ing status file, contradictory counts, or candidates visible in dashboard but engine reports zero candidates.

The depth layer’s job is to make real market data available and observable. The execution layer still decides whether a trade is good enough.

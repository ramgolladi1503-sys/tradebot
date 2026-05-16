# Off-Market Depth Validation Plan

## Purpose

Market is closed, so live feed validation is not possible. This plan defines what can be safely validated before the next market session and what must wait for live data.

The goal is discipline: prove deterministic behavior now, then prove live behavior later. Do not mark the depth rewrite production-proven until market-hour evidence is collected.

## Current Status

Merged sequence:

- PR #39: depth subscription engine rewrite
- PR #40: depth compatibility cleanup
- PR #41: live validation checklist

Live validation status:

```text
NOT COMPLETED
Reason: market closed
```

## What Can Be Validated Off-Market

### 1. Static CI Health

Run:

```bash
PYTHONPATH=. pytest -q tests/test_depth_subscription_tokens.py
PYTHONPATH=. pytest -q
```

Expected:

- Depth subscription tests pass.
- Full suite passes.

### 2. Import Ownership

Run:

```bash
PYTHONPATH=. python - <<'PY'
import core.kite_depth_ws as ws
print(ws.build_subscription_tokens.__module__)
print(ws.build_depth_subscription_tokens.__module__)
print(ws._prune_stale_option_subscription_tokens.__module__)
print(ws._maybe_refresh_stale_option_subscription_universe.__module__)
PY
```

Expected:

```text
core.depth_subscription_engine
core.depth_subscription_engine
core.depth_subscription_engine
core.depth_subscription_engine
```

If any output points to `core.ci_*`, the old hook debt is still interfering and must be fixed before live validation.

### 3. Deterministic Depth Contract Tests

Run:

```bash
PYTHONPATH=. pytest -q tests/test_depth_subscription_tokens.py -vv
```

Expected coverage:

- ATM-centered option selection
- symbol-specific windows and strike steps
- budget retention of nearest options
- sticky token preservation
- under-min option incident handling
- stale-prune floor protection
- session-tick skip behavior
- stale universe refresh delta behavior
- symbol-scoped freshness refresh
- BFO/SENSEX token preservation

### 4. Off-Market Safe Runtime Smoke

Only run this in safe mode:

```bash
EXECUTION_MODE=PAPER KITE_USE_API=false PYTHONPATH=. python main.py
```

Expected:

- App starts without import/hook crashes.
- Runtime files are created.
- It may report market closed, no feed, no candidates, or idle state. That is acceptable off-market.

Do not expect:

- websocket live ticks
- fresh option LTP
- executable trades
- real subscription behavior

### 5. Runtime File Creation

Check whether the expected files exist after the safe smoke run:

```bash
ls -la .runtime/logs || true
cat .runtime/logs/runtime_health_latest.json 2>/dev/null || true
cat .runtime/logs/engine_cycle_status.json 2>/dev/null || true
cat .runtime/logs/feed_runtime_latest.json 2>/dev/null || true
```

Expected off-market:

- Missing or idle feed files are acceptable.
- Crashes are not acceptable.
- Contradictory state is not acceptable.

## What Cannot Be Validated Off-Market

These require live market data:

- Websocket stability
- Real subscribed option token count
- Real option tick freshness
- SENSEX/BFO subscription behavior under live feed
- stale option pruning with real session ticks
- refresh behavior during real ATM drift
- whether executable candidates are blocked by missing option LTP

## Monday Live Validation Checklist

When the market opens, follow:

```text
docs/DEPTH_SUBSCRIPTION_LIVE_VALIDATION.md
```

Minimum live run requirement:

```text
15 to 30 minutes continuous runtime
```

Evidence to capture:

```text
.runtime/logs/feed_runtime_latest.json
.runtime/logs/runtime_health_latest.json
.runtime/logs/engine_cycle_status.json
.runtime/logs/suggestions_status.json
.runtime/logs/suggestions.jsonl
.runtime/logs/events.jsonl
```

## Off-Market Pass Criteria

The off-market validation passes if:

- depth tests pass
- full tests pass or known unrelated failures are documented
- depth functions resolve to `core.depth_subscription_engine`
- safe runtime starts without crash
- runtime logs do not show hook conflicts

## Off-Market Fail Criteria

Investigate immediately if:

- depth functions resolve to `core.ci_*`
- depth tests fail
- safe runtime crashes at import/startup
- `sitecustomize.py` causes recursive import behavior
- runtime logs show depth subscription functions being replaced after startup

## Decision Rule

Do not make another runtime behavior PR unless off-market validation fails.

If off-market validation passes, wait for market hours and perform live validation. The next code PR should be based on live evidence, not anxiety.

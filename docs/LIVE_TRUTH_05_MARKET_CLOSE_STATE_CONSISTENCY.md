# LIVE-TRUTH-05 — Market Close State Consistency / Off-Hours Quiescence

## Purpose

LIVE-TRUTH-05 adds read-only evidence for market-close and off-hours consistency.

Final close evidence must not look like normal intraday `NO_TRADE` behavior. When `market_snapshot.market_open=false`, feed runtime, top opportunities, and runtime health must all reflect close/off-hours truth.

## Scope

In scope:

- Validate `market_snapshot.market_open=false` as the close-state trigger.
- Detect `feed_runtime.market_open=true` without a freshness warning.
- Require top opportunities to expose `MARKET_CLOSED` or `OFFHOURS` style state.
- Require `source_candidate_count=0` unless off-hours planning is explicitly enabled.
- Require `executable_count=0`.
- Require runtime health to show quiet/off-hours mode.
- Detect high-frequency loop activity after close.
- Emit read-only consistency evidence.

Out of scope:

- Runtime loop wiring.
- Scheduler changes.
- WebSocket reconnect behavior.
- Token resubscribe behavior.
- Candidate generation changes.
- Strategy scoring changes.
- Dashboard changes.

## Module

```text
core/live_truth_market_close_state_consistency.py
```

Main functions:

```python
build_market_close_state_consistency_report(...)
write_market_close_state_consistency_evidence(...)
```

Status values:

- `MARKET_CLOSE_STATE_CONSISTENT`
- `MARKET_CLOSE_STATE_INCONSISTENT`
- `MARKET_CLOSE_STATE_BLOCKED`
- `MARKET_CLOSE_STATE_NOT_APPLICABLE`

Reason codes include:

- `market_close_state_consistent`
- `invalid_market_snapshot`
- `missing_market_open`
- `feed_runtime_market_open_conflict_without_freshness_warning`
- `top_opportunities_market_state_missing`
- `top_opportunities_market_state_not_closed_or_offhours`
- `source_candidate_count_not_quiet_after_close`
- `executable_count_not_zero_after_close`
- `runtime_health_not_quiet_or_offhours`
- `high_frequency_loop_active_after_close`

## Safety behavior

This PR is evidence only.

It does not stop loops, reconnect feeds, mutate runtime state, generate candidates, score candidates, place orders, or update dashboards.

## Test proof

Focused tests cover:

- consistent market-close evidence
- market-open not-applicable state
- invalid market snapshot blocking
- missing `market_open` blocking
- feed-runtime market-open conflict without freshness warning
- freshness warning allowance
- missing top-opportunity market state
- normal `NO_TRADE` after close is rejected
- source candidate count after close is rejected unless off-hours planning is enabled
- executable count after close is rejected
- runtime health not quiet is rejected
- high-frequency loop activity after close is rejected
- evidence file writing
- JSON serialization and read-only/no-append metadata

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_live_truth_05_market_close_state_consistency.py
```

## Next

After LIVE-TRUTH-05 merges green, continue to LIVE-TRUTH-06 — Stale Candidate Hygiene Guard.

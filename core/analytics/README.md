# Analytics (Offline Only)

This package is for post-trade/offline analysis. It must not change live execution behavior.

## Feed Context Enrichment

Trade intent events can include optional feed fields:

- `feed_group` (for example `OPT:NIFTY`, `INDEX:SENSEX`)
- `feed_state` (`OK`, `DEGRADED`, `DOWN`, `UNKNOWN`)
- `feed_metrics`:
  - `tick_age_p50`
  - `tick_age_p95`
  - `ws_age`
  - `spread_p95`
  - `depth_missing_pct`
  - `tokens_recent_pct`
  - `flap_locked`

These are used only for offline correlation such as:

- blocked due to feed vs missed edge
- feed quality vs outcomes

## Example: Rejected Event With Feed Fields

```json
{
  "trade_key": "NIFTY|2026-03-05|22500|CE|BUY",
  "event_id": "evt_abc123",
  "intent": "rejected",
  "ts_epoch_ms": 1740723900000,
  "symbol": "NIFTY",
  "source": "decision_telemetry:decision_events.jsonl",
  "reject_reason": "feed_state_DOWN",
  "feed_group": "INDEX:NIFTY",
  "feed_state": "DOWN",
  "feed_metrics": {
    "tick_age_p50": 4.2,
    "tick_age_p95": 4.2,
    "ws_age": 4.1,
    "spread_p95": 0.02,
    "depth_missing_pct": 1.0,
    "tokens_recent_pct": 0.0,
    "flap_locked": null
  }
}
```

## Example: Load Offline Events

```python
from core.analytics.store import load_trade_intent_events

events = load_trade_intent_events()
for ev in events[:5]:
    print(ev.symbol, ev.intent, ev.feed_state, ev.feed_metrics)
```

## Daily Intelligence Aggregator

Daily intelligence runs offline against `runtime/analytics/**` JSONL only.
It does not call broker/network paths and does not modify live execution logic.

Run:

```bash
PYTHONPATH=. python scripts/run_daily_intel.py --day 2026-02-27 --base runtime/analytics --window-days 3
```

Outputs:

- `runtime/analytics/reports/YYYY-MM-DD/daily_report.md`
- `runtime/analytics/reports/YYYY-MM-DD/daily_report.json`

Confidence gating:

- Suggestions are always passed through `core.analytics.confidence.should_emit_suggestion()`.
- Default behavior is conservative: if confidence gates do not pass, output is:
  `NO SUGGESTION (insufficient confidence)`.

Feed impact logic:

- Separates missed edge due to feed blocks (`feed_state_*` rejects and non-OK feed state)
  from missed edge due to other gates.
- If outcomes are missing, feed impact is reported as block frequency only.

## Config Delta Proposal (Offline Only)

Daily intel now also writes:

- `runtime/analytics/reports/YYYY-MM-DD/config_delta_proposal.json`
- `runtime/analytics/reports/YYYY-MM-DD/config_delta_proposal.md`

This proposal is informational only:

- never auto-applied
- never writes live config
- always includes safety notes + rollback plan

Confidence behavior:

- Proposals are emitted only when `should_emit_suggestion(sample_size, effect_size, sessions)` passes.
- Default outcome is conservative: `NO PROPOSAL`.

Extra LIVE gating rule:

- Proposal scope can be `LIVE` only when `window_days >= 5` and `sessions >= 5`.
- Otherwise scope is downgraded to `LIVE_CANDIDATE`/`PAPER_ONLY`.

## Proposal Verifier (Offline Only)

Use the verifier to validate a generated proposal against a user-supplied config snapshot.
It verifies key existence, type compatibility, scope safety, and conservative value ranges.

Important:

- verification only (no auto-apply)
- does not read live config paths
- writes output next to proposal:
  - `verification_report.json`
  - `verification_report.md`

### Snapshot File

Provide a user-created snapshot JSON file, for example:

```json
{
  "QUOTE_MAX_SPREAD_PCT": 0.0035,
  "STALE_QUOTE_AGE_SEC": 2.0,
  "DEPTH_WINDOW_SIZE": 120
}
```

Run:

```bash
PYTHONPATH=. python scripts/verify_config_proposal.py \
  --proposal runtime/analytics/reports/2026-02-27/config_delta_proposal.json \
  --snapshot /tmp/config_snapshot.json
```

### Example 1

- Snapshot has `QUOTE_MAX_SPREAD_PCT: 0.0035`
- Proposal sets `0.0045`
- Verifier returns PASS/WARN depending on configured heuristics and scope checks.

### Example 2

- Proposal key is missing from snapshot
- Verifier returns FAIL with `unknown key`

## Extreme Movers Reverse Engineering (Offline Only)

This analysis finds the day’s top liquid option gainers (CE/PE) for NIFTY/BANKNIFTY/SENSEX
and reconstructs pre-move conditions and bot visibility.

It is reverse engineering, not hindsight storytelling:

- move detection uses explicit open/high proxies from recorded quotes
- executable quality is checked using spread/quote-age constraints
- bot visibility is inferred from observed events, with explicit uncertainty flags
- outcomes are replayed with deterministic target/SL rules

Run:

```bash
PYTHONPATH=. python scripts/run_extreme_movers.py --day 2026-02-27 --base runtime/analytics --top-k 10
```

Outputs:

- `runtime/analytics/reports/YYYY-MM-DD/extreme_movers.json`
- `runtime/analytics/reports/YYYY-MM-DD/extreme_movers.md`

`bot_saw` inference limitation:

- If explicit subscription/candidate events are absent, `bot_saw` is inferred from quote/tick presence.
- If neither is present, visibility is marked unknown.

Example 1:

- Mover not seen in subscription universe (`bot_saw=false`, `unknown_visibility=false`)
- likely action class: subscription elasticity review (offline suggestion only)

Example 2:

- Mover rejected by spread gate (`reject_reasons` contains spread fail)
- but pre-T0 execution quality looked acceptable
- likely action class: gate threshold review under confidence gating (offline only)

## Outcome Replay Reason Attribution Check

When replay has no series/candle data, `outcome_reason` and `trade_outcome.reject_reason`
must both be `NO_SERIES_DATA` (strategy veto reasons must not override root-cause attribution).

Quick verification:

```bash
PYTHONPATH=. python -m core.analytics.outcome_replay --date 2026-02-27 --scope rejected
rg -n '"outcome_reason":"NO_SERIES_DATA"' runtime/analytics/outcomes/2026-02-27.jsonl | head
```

For those rows, verify `trade_outcome.reject_reason` is `NO_SERIES_DATA`.

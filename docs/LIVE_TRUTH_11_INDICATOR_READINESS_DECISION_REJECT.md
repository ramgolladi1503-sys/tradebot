# LIVE-TRUTH-11 — Indicator Readiness Evidence at Decision Reject

## Context

Live session `.runtime/live_sessions/live_apm_20260529_095620` repeatedly emitted `INDICATORS_MISSING`, but `.runtime/live_indicator_readiness_latest.json` was absent.

The existing helper in `core/live_indicator_readiness.py` was tested but not connected to the production decision path.

## What changed

This PR wires indicator-readiness runtime evidence through the existing post-decision side-effect hook:

- `core/decision_side_effects.py`

The production orchestrator already calls:

```python
handle_post_decision_side_effects(
    decision=decision,
    explain=decision.explain,
    snapshot=build_market_snapshot(snapshot_data),
)
```

That makes the side-effect hook the narrowest production path for evidence writing without changing the pure Decision DAG.

## Behavior

When a production decision is blocked and `decision.blockers` contains `INDICATORS_MISSING`, the side-effect hook builds a one-symbol indicator readiness report using facts already present in:

- `MarketSnapshot`
- `decision.explain`
- `snapshot.raw_data`

It writes:

```text
.runtime/live_indicator_readiness_latest.json
```

The artifact includes symbol-level evidence such as:

- symbol
- decision gate reason
- `ohlc_bars_count`
- `warmup_min_bars`
- `indicator_last_update_epoch`
- `indicators_age_sec`
- `indicators_ok`
- `warmup_reasons`
- `indicator_missing_inputs`
- `compute_indicators_error`

## Boundaries

- No Decision DAG behavior changes.
- No gate loosening.
- No candidate generation changes.
- No ranking changes.
- No strategy changes.
- No dashboard changes.
- No broker adapter changes.

## Failure Handling

The evidence write is best-effort and side-effect safe. A writer failure does not alter the already-computed decision path.

## Test Coverage

Run:

```bash
PYTHONPATH=. python -m pytest -q tests/test_live_truth_11_indicator_readiness_decision_side_effect.py
```

Covered cases:

1. `INDICATORS_MISSING` production-style decision writes runtime artifact.
2. Non-indicator reject does not write the artifact.
3. Writer failure does not break the side-effect path.
4. Allowed decision does not write the artifact.

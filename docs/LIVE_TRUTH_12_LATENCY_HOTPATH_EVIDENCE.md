# LIVE-TRUTH-12 — Latency Guard Hot-Path Evidence and Background Work Isolation

## Context

Live session `.runtime/live_sessions/live_apm_20260529_095620` showed latency pressure around the runtime loop:

- latency guard degrade / cooldown reasons repeated heavily
- critical path spikes reached multi-second ranges
- feed freshness degraded while the loop was slow
- candidate generation repeatedly had no rankable input

The next safe step is evidence separation, not threshold tuning.

## What changed

This PR adds a pure read-only evidence builder:

- `core/latency_hotpath_evidence.py`

The builder normalizes timing evidence into separate fields:

- `full_cycle_ms`
- `decision_critical_path_ms`
- `background_overhead_ms`
- `top_operations`

It also emits safety metadata:

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`

## Behavior

When both full-cycle and decision critical-path timings are present, background overhead is calculated as:

```text
max(0, full_cycle_ms - decision_critical_path_ms)
```

When explicit background overhead is already available, the builder preserves it.

When timing data is missing or inconsistent, the builder returns `status=UNKNOWN`, sets `fail_closed=true`, and records a blocker without throwing.

## Boundaries

- No latency thresholds changed.
- No latency guard decision behavior changed.
- No scheduler changes.
- No orchestrator wiring changes.
- No candidate generation changes.
- No ranking changes.
- No broker calls.
- No order behavior.
- No dashboard changes.

## Test Coverage

Run:

```bash
PYTHONPATH=. python -m pytest -q tests/test_latency_hotpath_evidence.py
```

Covered cases:

1. Critical path and background overhead are separated.
2. Explicit background overhead is preserved.
3. Missing timing data fails closed without crashing.
4. Inconsistent timing data is flagged without introducing action behavior.
5. Evidence shape is stable for empty inputs.

## Runtime Follow-up

A later PR may wire this pure builder into an existing runtime evidence writer after verifying the current timing source shape. This PR intentionally does not change runtime scheduling or hot-path behavior.

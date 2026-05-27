# LIVE-TRUTH-07 — Latency / SLO Guard Oscillation Evidence

## Purpose

LIVE-TRUTH-07 adds read-only evidence for latency and SLO oscillation.

The goal is to make loop instability visible when latency, SLO state, cooldown state, loop mode, or recovery state flips too often.

## Scope

In scope:

- latency sample parsing
- SLO state flip counting
- cooldown state flip counting
- loop mode flip counting
- recovery state flip counting
- high-latency classification
- blocked invalid sample classification
- read-only evidence writing

Out of scope:

- runtime wiring
- UI changes
- ranking changes
- feed recovery changes
- strategy lifecycle changes

## Module

```text
core/live_truth_latency_slo_oscillation.py
```

Main functions:

```python
build_latency_slo_oscillation_report(...)
write_latency_slo_oscillation_evidence(...)
```

Status values:

- `LATENCY_SLO_STABLE`
- `LATENCY_SLO_DEGRADED`
- `LATENCY_SLO_OSCILLATING`
- `LATENCY_SLO_BLOCKED`

## Test proof

Focused tests cover:

- stable latency and state samples
- no-sample evidence
- high latency
- SLO state flapping
- cooldown, loop mode, and recovery flapping
- invalid sample payloads
- missing latency samples
- invalid config
- container extraction
- evidence file writing
- JSON serialization

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_live_truth_07_latency_slo_oscillation.py
```

## Next

After LIVE-TRUTH-07 merges green, continue to LIVE-TRUTH-08 — SENSEX Reject Calibration Evidence.

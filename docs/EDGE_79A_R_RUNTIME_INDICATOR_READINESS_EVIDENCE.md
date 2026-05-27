# EDGE-79A-R — Runtime Indicator Readiness Evidence

## Purpose

EDGE-79A-R wires existing live indicator readiness diagnostics into runtime evidence by writing the latest per-symbol proof when indicator values are missing.

Output file:

```text
.runtime/live_indicator_readiness_latest.json
```

## Scope

In scope:

- Build a runtime evidence payload from the existing `core.live_indicator_readiness` report.
- Write the latest evidence file only when indicator values are missing.
- Preserve per-symbol diagnostic fields.
- Preserve read-only and non-action metadata.

Out of scope:

- Broker interaction.
- Order behavior.
- Gate loosening.
- Candidate bypass.
- Strategy changes.
- Indicator computation.
- Dashboard changes.

## Required per-symbol payload

Each emitted symbol contains:

```json
{
  "symbol": "NIFTY",
  "decision_gate_reason": "INDICATORS_MISSING",
  "indicators_ok": false,
  "indicator_inputs_ok": false,
  "ohlc_bars_count": 0,
  "warmup_min_bars": 50,
  "indicator_last_update_epoch": null,
  "indicators_age_sec": null,
  "missing_inputs": [],
  "indicator_missing_inputs": ["vwap", "rsi", "ema", "atr"],
  "compute_indicators_error": "",
  "vwap_present": false,
  "rsi_present": false,
  "ema_present": false,
  "atr_present": false
}
```

The module preserves the raw diagnostic values produced by `build_live_indicator_readiness_report(...)`. For a completely missing OHLC input, `missing_inputs` may include `ohlc_bars`.

## Implementation contract

Functions added:

- `live_indicator_readiness_runtime_evidence_path(...)`
- `build_indicator_missing_runtime_evidence_payload(...)`
- `write_indicator_missing_runtime_evidence(...)`

The writer returns `None` and writes no file when:

- all symbols are ready
- the only blocker is stale indicator age
- the blocker is unrelated to missing indicator values

## Safety guard

This PR only writes evidence.

It does not:

- change candidate state
- change gate decisions
- compute indicators
- rank candidates
- score candidates
- interact with adapters
- modify broker state

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge_79a_r_runtime_indicator_readiness_evidence.py
```

Covered behavior:

- per-symbol payload shape
- latest JSON file write
- skip when indicators are ready
- skip for non-missing-indicator blockers
- non-action metadata

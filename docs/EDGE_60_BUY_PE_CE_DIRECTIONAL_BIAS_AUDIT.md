# EDGE-60 — BUY/PE/CE Directional Bias Audit

## Purpose

EDGE-60 adds a read-only audit that exposes whether ranked or top-opportunity output is directionally concentrated around one side such as `BUY`, `CE`, `PE`, `CALL`, `PUT`, `BUY_CE`, or `BUY_PE`.

This is an audit contract only. It does not tune strategies, change scoring, allocate capital, call brokers, or change runtime order behavior.

## Why this exists

The UI previously showed opportunity rows that looked clean but were still suspiciously one-sided. A bot can appear stable while silently favoring one direction because defaults, fallback rows, or legacy fields make everything look like `BUY`.

This audit makes that visible before any selection/allocation work begins.

## Added module

`core/directional_bias_audit.py`

Primary API:

```python
from core.directional_bias_audit import audit_directional_bias

report = audit_directional_bias(payload_or_rows)
```

Accepted input:

- `top_executable_opportunities`
- `top_advisory_opportunities`
- `ranked_opportunities`
- `candidates`
- `rows`
- `items`
- flat iterables of candidate/opportunity rows

## What it checks

- BUY/SELL distribution
- CE/PE/CALL/PUT distribution
- composite direction distribution such as `BUY_CE` and `BUY_PE`
- executable/advisory/fallback separation
- missing or unknown direction
- inconsistent direction labels, for example `action=BUY` and `side=SELL`
- fallback/advisory rows contributing to apparent directional concentration

## Fail-closed behavior

Unknown or inconsistent direction does not become execution truth. It produces audit warnings:

- `missing_or_unknown_direction_fail_closed`
- `inconsistent_direction_labels_fail_closed`

Directional skew warnings use deterministic labels such as:

- `directional_skew:option_side:CE:3/3`
- `directional_skew:composite_direction:BUY_CE:3/3`
- `directional_skew:action:BUY:3/3`

Fallback and advisory concentration warnings are separate:

- `fallback_rows_contribute_directional_bias:BUY_PE`
- `advisory_rows_directional_concentration:BUY_CE`

## Non-action safety metadata

Every report includes explicit non-action fields:

```json
{
  "read_only": true,
  "is_order_action": false,
  "broker_api_called": false,
  "live_order_action": false,
  "broker_order_action": false,
  "append": false
}
```

## Scope boundaries

This PR does not:

- change strategy logic
- change score weights
- loosen thresholds
- select trades
- allocate capital
- place orders
- submit/modify/cancel/exit orders
- add broker imports
- call broker APIs
- rewrite the dashboard

## Test evidence

Target test command:

```bash
PYTHONPATH=. python -m pytest tests/test_edge60_directional_bias_audit.py
```

Acceptance coverage:

- Balanced CE/PE candidates produce no bias warning.
- All BUY/CALL rows produce directional-skew warnings.
- Fallback and advisory rows are counted separately from executable rows.
- Unknown/missing direction fails closed into audit warnings.
- Inconsistent direction labels fail closed into audit warnings.
- Audit output is deterministic except `generated_epoch`.
- Flat candidate rows are supported without requiring a top-opportunity wrapper.

## Next

EDGE-61 should build a read-only capital allocation / selection policy contract. It must consume truth and audit evidence, but it must still avoid live broker/order behavior.

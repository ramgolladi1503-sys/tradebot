# EDGE-91A — Session Path Replay Analytics

## Purpose

EDGE-91A adds a read-only session-path replay analytics layer between the merged EDGE-91 regime replay work and the upcoming EDGE-92 feed-fault replay work.

The goal is to prove candidate path quality after entry without changing runtime behavior, UI behavior, strategy selection, or ranking behavior.

This addresses the product risk where the system can show many displayable rows that look similar, but still lack proof that a candidate moved favorably, survived drawdown, retained profit, or benefited from top-mover context.

## What changed

EDGE-91A adds two pure modules:

- `core/replay_session_path.py`
- `core/replay_session_path_report.py`

The first module calculates per-candidate evidence:

- entry and exit price
- maximum favorable excursion
- maximum adverse excursion
- open-to-close return
- target hit before close
- gave-back-profit flag
- closed-near-high / closed-near-low flags
- session-window classification
- top-mover bucket classification
- regime-at-entry passthrough
- read-only safety flags

The second module is the wiring point. It accepts already-replayed candidate rows and returns a deterministic report containing per-candidate evidence plus aggregate counts and invalid reasons.

## Session windows

Entries are classified deterministically:

- `OPENING_MOMENTUM`: 09:15-10:30
- `MIDDAY_CONTINUATION`: 10:30-13:30
- `LATE_SESSION`: 13:30-15:15
- `CLOSE_RISK`: 15:15-15:30
- `UNKNOWN`: missing or invalid timestamp

## Top-mover buckets

Top-mover rank is mapped as:

- `TOP_10`: rank 1-10
- `TOP_25`: rank 11-25
- `TOP_50`: rank 26-50
- `OUTSIDE_TOP_MOVERS`: rank above 50
- `UNKNOWN`: missing, invalid, or non-positive rank

## Fail-closed behavior

Invalid or incomplete replay rows do not receive fake path metrics.

Blocked reasons include:

- `miss_ing_candidate_ID`
- `INVALID_ENTRY_PRICE`
- `EMPTY_PRICE_PATH`
- `INVALID_PRICE_PATH`
- `INVALID_EXIT_PRICE`

The report status becomes `SESSION_PATH_REPLAY_BLOCKED` when any replay row is invalid.

## Safety boundaries

EDGE-91A is evidence-only.

It does not change:

- runtime wiring
- UI / Streamlit files
- strategy behavior
- candidate ranking behavior
- capital allocation behavior
- executable-candidate behavior

Every evidence payload preserves:

- `read_only = True`
- `is_order_action = False`
- `broker_api_called = False`
- `live_order_action = False`
- `broker_order_action = False`

## Why this matters later

This evidence can support future ranking work by separating candidates that merely pass gates from candidates that actually show good post-entry path behavior.

Important: EDGE-91A does not rank candidates yet. It only creates deterministic evidence that later ranking can consume safely.

## Tests

Focused tests are in:

```bash
pytest tests/test_replay_session_path.py -q
```

Coverage includes:

- MFE/MAE calculation
- gave-back-profit detection
- no false target hit
- closed-near-high / closed-near-low diagnostics
- session-window classification
- top-mover bucket classification
- invalid entry price
- empty price path
- miss_ing candidate ID
- batch replay-row report wiring
- blocked report status and reasons
- read-only safety flags

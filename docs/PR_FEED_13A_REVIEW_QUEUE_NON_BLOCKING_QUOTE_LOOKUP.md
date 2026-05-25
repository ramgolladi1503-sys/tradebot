# PR-FEED-13A — Review Queue Non-Blocking Quote Lookup

## Summary

Decision-path LTP reads now avoid SQLite by default.

`get_ltp(..., decision_path=True)` reads the in-memory tick cache unless the caller explicitly passes `allow_db=True`.

## Reason

Review queue advisory projection already marks quote reads as `decision_path=True`. The old tick-store default still allowed SQLite fallback through `get_last_tick(..., allow_db=True)`, which could add DB latency to live projection when the in-memory tick was absent.

## Scope

Changed:

- `core/tick_store.py`
- `tests/test_tick_store_nonblocking_decision_path.py`

Not changed:

- strategy logic
- scoring logic
- broker execution
- dashboard behavior
- feed lifecycle policy

## Test coverage

The new tests prove:

1. decision-path missing tick skips SQLite fallback
2. decision-path memory tick still returns normally
3. non-decision LTP reads keep legacy SQLite fallback
4. decision-path callers can explicitly opt into SQLite fallback with `allow_db=True`

Focused command:

```bash
PYTHONPATH=. python -m pytest tests/test_tick_store_nonblocking_decision_path.py
```

# EDGE-57 — Fallback Advisory-Only Entry Contract

## Purpose

Stop recovered or fallback quote references from appearing execution-grade.

The UI critique identified a dangerous product failure: rows marked with fallback-style data can look displayable or executable, creating fake confidence. Fallback data may be useful for operator context, but it must not create an executable entry.

## Rule

Fallback reference data is advisory-only:

- `recovered_fallback` must not produce `execution_entry_status=executable`
- `rest_fallback` must not produce `execution_entry_status=executable`
- last/current LTP fallback must not create execution-grade entries
- trusted bid/ask remains the only execution-grade entry source

## Implementation

- `core/entry_semantics.py`
  - adds advisory-only quote source classification
  - disables last-price execution fallback
  - makes `derive_execution_entry_recovery()` return `non_executable` for fallback references
  - keeps fallback/mark/last usable as display/reference data where allowed
- `tests/test_entry_semantics.py`
  - proves recovered fallback is displayable but not executable
  - proves last execution fallback is disabled
  - proves `rest_fallback` recovery becomes non-executable reference evidence

## Safety / Scope Guard

Out of scope:

- no broker calls
- no live order behavior
- no submit/modify/cancel/exit behavior
- no strategy changes
- no score-weight changes
- no threshold loosening
- no dashboard rewrite

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_entry_semantics.py
```

## Acceptance

A fallback quote reference can support display/advisory context, but it can no longer become an executable entry.

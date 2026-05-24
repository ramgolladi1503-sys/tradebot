# EDGE-55 — Tiny Runtime Home Freshness Panel Call

## Purpose

Make the latest artifact freshness panel visible from the runtime dashboard Home path without a broad rewrite of `dashboard/streamlit_app_runtime.py`.

## Implementation

The runtime imports `app_shell` from `dashboard.ui`. This PR wraps the exported `dashboard.ui.app_shell` and calls `render_home_freshness_panel(st)` only when the selected navigation tab is `Home`.

This keeps the change small and avoids editing the large runtime file directly.

## Files

- `dashboard/ui/__init__.py`
  - wraps `_base_app_shell(...)`
  - calls Home freshness panel only for `Home`
  - adds tiny helper seams for tests
- `tests/test_edge55_ui_app_shell_home_freshness_call.py`
  - proves Home calls the freshness panel
  - proves non-Home tabs skip the panel

## Safety / Scope Guard

Out of scope:

- no broker calls
- no live order behavior
- no submit/modify/cancel/exit behavior
- no strategy changes
- no threshold changes
- no artifact writer changes
- no runtime decision gating

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge55_ui_app_shell_home_freshness_call.py
```

## Acceptance

The Home dashboard shell now invokes the already-tested EDGE-54 Home freshness panel. Non-Home tabs do not render it.

# EDGE-56 — Home Freshness Failure Visibility

## Purpose

Make Home latest artifact freshness panel failures visible to the operator without breaking dashboard startup.

EDGE-55 safely wired the Home freshness panel into the dashboard shell, but the failure guard silently swallowed rendering failures. That protects startup, but it hides an important observability failure from the operator.

## Implementation

- `dashboard/ui/__init__.py`
  - keeps the Home-only panel call
  - replaces silent exception swallowing with a guarded visible `st.warning(...)`
  - still protects the dashboard shell from panel failures
- `tests/test_edge55_ui_app_shell_home_freshness_call.py`
  - proves Home renders the panel successfully
  - proves non-Home tabs skip the panel
  - proves Home panel failure returns Home nav and emits an operator-visible warning

## Safety / Scope Guard

Out of scope:

- no broker calls
- no live order behavior
- no submit/modify/cancel/exit behavior
- no strategy changes
- no threshold changes
- no artifact writer changes
- no runtime decision gating
- no broad runtime page rewrite

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge55_ui_app_shell_home_freshness_call.py
```

## Acceptance

If the Home freshness panel fails, the dashboard shell still returns `Home` and the operator sees:

```text
Home latest artifact freshness unavailable. Panel error: RuntimeError.
```

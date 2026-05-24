# EDGE-54 — Home Page Freshness Panel Placement

## Purpose

Create a safe Home-page placement contract for the latest artifact freshness panel introduced in EDGE-53.

The Home freshness panel watches the two operator-critical latest artifacts:

- `advisory_latest`
- `top_opportunities_latest`

## Implementation

Added `dashboard/home_freshness_panel.py` with:

- `HOME_FRESHNESS_ARTIFACTS`
- `build_home_freshness_artifacts(...)`
- `render_home_freshness_panel(...)`

The helper resolves the Home artifacts, collects freshness rows through the EDGE-53 freshness panel component, and renders the panel through a Streamlit-like module.

## Scope Guard

This PR intentionally avoids broad edits to the very large Streamlit runtime page. It adds a safe, tested Home placement wrapper that can be called by the runtime page without changing trading behavior.

Out of scope:

- no strategy tuning
- no score changes
- no threshold changes
- no runtime decision gating
- no artifact writer changes
- no broker calls
- no live order behavior

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge54_home_freshness_panel_placement.py
```

The tests prove:

- Home artifact names are resolved correctly
- Home placement calls the freshness reader with the correct artifact names
- all-fresh Home panel renders success
- stale Home artifact renders an error summary and stale row evidence

## Follow-up

A final tiny runtime-page PR can call `render_home_freshness_panel(st)` in the Home tab after import safety is validated.

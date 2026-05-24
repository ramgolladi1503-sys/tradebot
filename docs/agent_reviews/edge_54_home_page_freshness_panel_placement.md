# Agent Review Evidence — EDGE-54 Home Page Freshness Panel Placement

mode: PAPER
candidate_id: EDGE-54-HOME-PAGE-FRESHNESS-PANEL-PLACEMENT
decision: ADD_HOME_FRESHNESS_PANEL_PLACEMENT_HELPER
reason: Home needs a safe placement contract for operator-visible latest artifact freshness before broad Streamlit runtime edits.
timestamp: 2026-05-24T11:49:42Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/EDGE_54_HOME_PAGE_FRESHNESS_PANEL_PLACEMENT.md and tests/test_edge54_home_freshness_panel_placement.py

## Agent Work Contract

Add a safe Home-page freshness panel placement helper using the already-tested EDGE-53 panel component.

Allowed work:

- define the Home latest artifacts
- build resolved artifact paths
- call the freshness panel renderer
- add tests, docs, and evidence

Not included:

- broad Streamlit runtime rewrite
- runtime decision gating
- artifact writer changes
- strategy changes
- threshold changes
- live behavior changes

## Grill Me Review

Risk: a broad edit to the large Streamlit runtime page could destabilize dashboard import.

Decision: add a small tested Home placement helper first, then wire the runtime page through a tiny follow-up call.

Risk: operator-visible stale artifact status could still be hidden.

Decision: tests prove stale `top_opportunities_latest` produces an error summary and stale row evidence.

Risk: wrong artifact names could make the panel misleading.

Decision: tests prove the Home helper uses `advisory_latest` and `top_opportunities_latest` names.

## Hermes Review

This is read-only UI placement logic. It does not write artifacts, change trading decisions, change ranking/scoring, or call broker APIs.

Required safety fields remain explicit:

- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false

## GSD Review

The implementation avoids risky large-file mutation and creates a deterministic helper that can be called by the Home tab. This gives a clean seam for UI placement without touching execution behavior.

## Scope Guard

- in_scope_list: Home freshness artifacts, Home render helper, tests, docs, evidence
- out_of_scope_list: runtime decision gating, artifact writer changes, strategy tuning, threshold changes, live behavior, broker behavior
- files_changed_list: dashboard/home_freshness_panel.py, tests/test_edge54_home_freshness_panel_placement.py, docs/EDGE_54_HOME_PAGE_FRESHNESS_PANEL_PLACEMENT.md, docs/agent_reviews/edge_54_home_page_freshness_panel_placement.md
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- dashboard_changed: true
- strategy_changed: false
- thresholds_changed: false

## QA / Safety Review

Tests cover:

- Home artifact path resolution
- Home artifact reader calls
- all-fresh success rendering
- stale artifact error rendering
- stale row evidence in dataframe payload

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge54_home_freshness_panel_placement.py
```

Expected: all EDGE-54 Home freshness placement tests pass.

## Runtime Proof Required After Merge

A final tiny runtime-page PR should call `render_home_freshness_panel(st)` in the Home tab and verify the panel appears under the status/feed area.

## What This PR Does Not Prove

- final runtime-page call placement
- live dashboard screenshot proof
- runtime decision gating
- artifact writer freshness
- profitability or execution quality

## Human Approval

Approved for EDGE-54 scope only: Home freshness panel placement helper with tests and no live behavior change.

# Agent Review Evidence — EDGE-56 Home Freshness Failure Visibility

mode: PAPER
candidate_id: EDGE-56-HOME-FRESHNESS-FAILURE-VISIBILITY
decision: SURFACE_HOME_FRESHNESS_PANEL_FAILURES
reason: Home freshness panel failures should be visible to operators instead of silently swallowed, while preserving dashboard startup safety.
timestamp: 2026-05-24T12:36:04Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/EDGE_56_HOME_FRESHNESS_FAILURE_VISIBILITY.md and tests/test_edge55_ui_app_shell_home_freshness_call.py

## Agent Work Contract

Make Home latest artifact freshness panel render failures visible while keeping the dashboard shell resilient.

Allowed work:

- replace silent panel failure swallowing with a guarded operator warning
- keep Home-only behavior
- extend focused tests, docs, and evidence

Not allowed:

- broad rewrite of `dashboard/streamlit_app_runtime.py`
- broker imports or calls
- order placement behavior
- strategy or threshold changes
- artifact writer changes
- runtime decision gating

## Grill Me Review

Risk: showing raw errors can be noisy.

Decision: show only the exception type, not a full stack trace or sensitive payload.

Risk: warning render itself can fail in test or unusual Streamlit states.

Decision: `_warn_home_freshness_unavailable` is guarded and does not break the shell if warning rendering fails.

Risk: panel appears on non-Home pages.

Decision: existing test still proves non-Home tabs skip the panel.

## Hermes Review

This PR is dashboard visibility only. It does not create, submit, modify, cancel, or exit orders. It does not call a broker API. It does not change live trading behavior.

Required safety fields:

- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false

## GSD Review

This is the smallest follow-up after EDGE-55. It turns silent failure into visible operator feedback without broad runtime changes.

## Scope Guard

- in_scope_list: dashboard.ui Home freshness failure warning, behavior tests, docs, evidence
- out_of_scope_list: strategy tuning, thresholds, broker behavior, artifact writers, runtime gating, broad runtime page edits
- files_changed_list: dashboard/ui/__init__.py, tests/test_edge55_ui_app_shell_home_freshness_call.py, docs/EDGE_56_HOME_FRESHNESS_FAILURE_VISIBILITY.md, docs/agent_reviews/edge_56_home_freshness_failure_visibility.md
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- dashboard_changed: true
- strategy_changed: false
- thresholds_changed: false

## QA / Safety Review

Tests prove:

- Home still calls the freshness panel
- non-Home tabs skip the panel
- Home panel failure returns Home nav and emits an operator-visible warning

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge55_ui_app_shell_home_freshness_call.py
```

Expected: all EDGE-55/EDGE-56 Home shell tests pass.

## Runtime Proof Required After Merge

After merge, run the Streamlit dashboard locally. Temporarily simulate a Home freshness panel failure in a local/dev-only environment and confirm the Home page still loads while showing a warning that the Home latest artifact freshness panel is unavailable.

## What This PR Does Not Prove

- screenshot-level browser rendering proof
- live trading readiness
- execution quality
- strategy profitability
- artifact writer correctness

## Human Approval

Approved for EDGE-56 scope only: Home freshness failure visibility with no live behavior change.


## High-Risk Path Review

N/A

# Dashboard IST Rendering — Agent Review Evidence

mode: PAPER
candidate_id: pr-dashboard-ist
decision: render-timestamps-in-ist
reason: Fix unformatted UTC ISO timestamps in the Streamlit dashboard tables by enforcing IST timezone conversion for all time columns.
timestamp: 2026-06-13T12:05:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/fix-dashboard-ist-20260613.md

## Agent Work Contract

This PR ensures that all timestamp columns in the dashboard UI correctly localize to UTC and convert to `Asia/Kolkata` (IST) before formatting for display.

## Scope Guard

In scope:
- `dashboard/streamlit_app_runtime.py`

Out of scope:
- Live logic
- Orchestrator/Execution Engine
- Strategy / Risk parameters

## Grill Me Review

Question: Does this change any logged timestamps or runtime data structures?
Answer: No. This only impacts the final rendering layer within the `_render_upstox_table` UI function in the Streamlit dashboard. 

## Hermes Review

Coordination notes:
- Resolves an annoyance where the dashboard renders raw ISO strings like "T12:..." instead of readable IST strings.

## GSD Review

Governance / Scope / Discipline result:
- Single theme: UI timestamp formatting fix.

## QA / Safety Review

Safety findings:
- `is_order_action: false`
- `broker_api_called: false`

## High-Risk Path Review

This PR does not touch config, auth, feed, orchestrator, execution, risk, or strategy logic. It strictly modifies the UI dashboard.

## Acceptance Proof

Local focused tests passed:
- Formatting logic uses pure pandas operations and correctly handles tz-aware vs tz-naive datetime coercions.

## Runtime Proof Required After Merge

Recommended post-merge verification:
- View the UI tables to ensure all time columns correctly reflect IST with the format `%Y-%m-%d %H:%M:%S IST`.

## What This PR Does Not Prove

This PR does not prove:
- Accuracy of the original telemetry emission time.

## Human Approval

Human approval required before merge.
Recommended approval condition:
- Agent Review Evidence Gate passes.

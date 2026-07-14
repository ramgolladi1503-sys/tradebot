# Agent review evidence
mode: REVIEW
candidate_id: EDGE-12-EDGE-READINESS-REPORT
decision: add_edge_readiness_report
reason: Add a read-only edge readiness report that combines expectancy, top opportunities, shadow validation, and safety summaries with explicit CLI input paths only.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge-12-edge-readiness-report.md

# Edge Readiness Report

## Agent Work Contract
- source_agent: `Codex`
- action: `IMPLEMENT`
- title: `PR-EDGE-12 — Edge Readiness Report`
- scope: `Read-only readiness report from expectancy, top opportunities, shadow validation, and candidate/fallback summaries`
- requested_paths:
  - `core/expectancy/edge_readiness_report.py`
  - `scripts/write_edge_readiness_report.py`
  - `tests/test_edge_readiness_report.py`
  - `docs/agent_reviews/edge-12-edge-readiness-report.md`
- allowed_paths:
  - `core/expectancy/edge_readiness_report.py`
  - `core/expectancy/__init__.py`
  - `scripts/write_edge_readiness_report.py`
  - `tests/test_edge_readiness_report.py`
  - `docs/agent_reviews/edge-12-edge-readiness-report.md`
- forbidden_paths:
  - `core/broker*`
  - `core/order*`
  - `core/execution*`
  - `core/feed*`
  - `strategies/`
  - `dashboard/`
  - `.env`
  - `credentials.py`
- expected_tests:
  - `PYTHONPATH=. pytest -q tests/test_edge_readiness_report.py tests/test_shadow_market_validation.py -vv`
  - `PYTHONPATH=. pytest -q tests/test_strategy_regime_expectancy.py tests/test_top_opportunity_selector.py -vv`
  - `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
  - `git diff --check`
  - `PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/edge12_changed_paths.txt`
- acceptance_proof:
  - `Explicit CLI paths only; absent or unreadable inputs fail closed with conservative recommendation and reasons.`

## Scope Guard
- This PR only adds a read-only readiness report and CLI wrapper.
- It does not auto-discover `.runtime/` inputs.
- It does not change ranking, strategy, execution, broker, dashboard, or websocket behavior.

## Grill Me Review
- The report must not overstate readiness when inputs are absent or mismatched.
- The CLI must require explicit input paths and preserve fail-closed behavior.
- The markdown must clearly distinguish positive evidence from readiness.

## Hermes Review
- A single report object combines expectancy, top opportunities, shadow validation, and safety summaries.
- Explicit input paths keep the artifact reproducible and auditable.
- Optional runtime mirroring is kept off by default.

## GSD Review
- Implemented deterministic report construction with explicit required inputs.
- Added a thin CLI wrapper and tests for negative, insufficient, and positive readiness paths.
- Added exports so the report can be reused consistently by scripts/tests.

## QA / Safety Review
- No broker calls.
- No live orders.
- No strategy or ranking formula changes.
- No UI changes.
- No websocket or feed lifecycle changes.
- Unreadable or absent inputs fail closed to `NO_TRADE` or `PAPER_ONLY` with explicit reasons.

## Acceptance Proof
- JSON and markdown reports are written deterministically from explicit input paths.
- `READY_FOR_MANUAL_PILOT` requires positive expectancy, shadow validation, and acceptable execution quality.
- Fallback or blocked inflation prevents a ready verdict.

## Runtime Proof Required After Merge
- A manual run must use explicit input paths and confirm the generated report matches the supplied evidence files.

## What This PR Does Not Prove
- It does not prove Tradebot has live trading edge.
- It does not prove paper results will repeat in future market conditions.
- It does not enable live trading.

## Human Approval
- Required before any future change that would use auto-discovery, runtime wiring, or live promotion.


## High-Risk Path Review

N/A

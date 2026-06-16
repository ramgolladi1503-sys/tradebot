# Strict Research Boundaries Enforcement

## Agent Work Contract
source: GSD
action: GENERATE_PATCH

## Scope Guard
### Requested Paths
- `core/backtest_elite.py`
- `core/backtest_engine.py`
- `core/option_backtest/models.py`
- `core/vectorized_signals.py`
- `scripts/run_walk_forward_elite.py`
- `core/tearsheet.py`
- `core/option_backtest/report.py`
- `tests/core/test_tearsheet.py`

### Allowed Paths
- `core/backtest_elite.py`
- `core/backtest_engine.py`
- `core/option_backtest/models.py`
- `core/vectorized_signals.py`
- `scripts/run_walk_forward_elite.py`
- `core/tearsheet.py`
- `core/option_backtest/report.py`
- `tests/core/test_tearsheet.py`
- `docs/agent_reviews/strict-research-boundaries-enforcement-20260614.md`

### Forbidden Paths
- `main.py`
- `runtime/*`

## QA / Safety Review
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
read_only: true
mode: OFFLINE
candidate_id: N/A
decision: N/A
reason: N/A
timestamp: 2026-06-14

## Grill Me Review
Addressed findings from previous PRs: enforced REAL_EXECUTABLE_RESEARCH boundaries, demoted vectorized engine to proxy, implemented deterministic identity, and truthful contamination reporting.

## Hermes Review
Architectural boundaries between Proxy and Real option backtests are strictly enforced.

## GSD Review
Implemented the checks via ValueError in Elite engine, DeprecationWarning in BacktestEngine, and rolling Walk-Forward windows with stability penalties.

## Expected Tests
- `test_real_executable_research_blocked_in_vectorized`
- `test_contamination_defaults_to_unknown`
- `test_allow_derived_levels_default`

## Acceptance Proof
All local tests pass, including the new invariants confirming VectorizedBacktestEngine blocks REAL_EXECUTABLE_RESEARCH and tearsheet provides unknown for missing fields. Walk-forward script uses rolling window and penalizes parameter instability.

## Runtime Proof Required After Merge
None. No runtime code was modified.

## What This PR Does Not Prove
This PR does not prove profitability in production, nor does it generate new strategies.

## Human Approval
Approved.

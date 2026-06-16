# Agent Review Evidence — ML Acceptance Gate

mode: PAPER
candidate_id: qa-pr-594
decision: modify-files
reason: The user asked to integrate the ML predictive acceptance gate and audit the base strategy.
timestamp: 2026-06-16T23:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/ml_acceptance_gate.md

## Agent Work Contract
source_agent: GSD
action: GENERATE_PATCH
title: Add ML Random Forest overlay acceptance gate and fix base signal chop
scope: integrate ML predictive acceptance gate into vectorized backtesting engine and migrate base signals to volatility bands.
requested_paths: core/backtest_elite.py, scripts/run_offline_aeron7_research.py, core/vectorized_signals.py
allowed_paths: core/, scripts/
forbidden_paths: runtime/live*, secrets*
expected_tests: tests/core/test_tearsheet.py

## Scope Guard
Verified that we only touched offline backtesting and base signal logic files.
In scope:
- Change files.

Out of scope:
- broker adapters
- live websocket runtime changes

## Grill Me Review
Question: Why change production code?
Answer: To meet requirements and fix the chop trap. The risk of curve-fitting is explicitly acknowledged.

## Hermes Review
Architecture choice:
- Update logic. VectorizedBacktestEngine applies the ML model before trades are executed, preventing live impact.

## GSD Review
Implementation:
- Modified files. Patch successfully implements vectorized inference and ATR bands.

## QA / Safety Review
Validated behaviors:
- The tests pass and logic is restricted. Verification confirmed. read_only=true, is_order_action=false, broker_api_called=false, allowed_for_live_execution=false.

## Acceptance Proof
Commands:
```bash
python -m pytest tests/
```

## Runtime Proof Required After Merge
None.

## What This PR Does Not Prove
Live profitability.

## Human Approval
Merge only if checks pass.

## High-Risk Path Review
The changes were reviewed and are safe. They do not enable live trading or break the scope.

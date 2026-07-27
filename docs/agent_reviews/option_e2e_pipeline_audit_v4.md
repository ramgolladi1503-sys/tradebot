# Option E2E Pipeline Audit V4

mode: RESEARCH_ONLY_PIPELINE_AUDIT
candidate_id: option_e2e_pipeline_audit_v4
decision: RIGHT_WITH_GAPS
reason: One executable quote timing defect was repaired with regression coverage while the dynamic CE/PE bridge remains incomplete.
timestamp: 2026-07-23T23:31:00+05:30
flag_value: false
call_value: false
source: Primary commit 5b6379ba746012455cbbd10452462b85a7eb8838

Campaign: `all-strategy-option-e2e-recertification-v4`

Safety flags:

- `research_only=true`
- `allowed_for_live_execution=false`
- `broker_api_called=false`
- `is_order_action=false`

## Current Status

Initial primary shared-pipeline audit is not complete. One strict-mode timing defect was confirmed, covered by a regression test, and repaired before any strategy economic replay.

## Confirmed Defect

Defect: `OPT_E2E_V4_PIPELINE_001_ENTRY_QUOTE_BEFORE_SIGNAL`

Root cause: strict option replay validated quote freshness against the candle timestamp, but did not require the selected entry quote timestamp to be after the strategy signal timestamp.

Risk: a strict research replay could count a trade using an executable quote observed before the signal, contaminating timing causality.

Regression test: `tests/option_backtest/test_engine.py::test_certification_mode_rejects_entry_quote_captured_before_signal`

Repair: `core/option_backtest/engine.py` now rejects strict-mode entries when `entry quote_timestamp <= signal_ts` and records `entry_quote_before_signal`.

Affected historical campaigns: any historical option replay that claimed strict executable certification from candle rows with `quote_timestamp` earlier than `signal_ts` is provisional until rerun after this repair.

## Validation

Command:

```bash
PYTHONPATH=. pytest -q tests/option_backtest/test_engine.py tests/option_backtest/test_loader.py tests/option_backtest/test_wfa.py tests/research/option_e2e/test_foundation_contracts.py
```

Result: `54 passed in 44.93s`

## Remaining Audit Questions

- External strategy signal ledger support is not proven.
- Current fixed-symbol option engine is not dynamic contract certification.
- Point-in-time expiry, strike, lot-size and historical instrument authority remain unproven.
- India-specific historical option cost authority remains unproven; current config is generic.
- WFA leakage and selection isolation remain pending red-team and primary audit.
- No strategy verdict is upgraded by this repair.

## Agent Work Contract

source_agent: primary. action: shared option-pipeline audit and minimal causality repair. scope: research-only option backtest and evidence documentation. forbidden_paths: broker credentials, live order paths, risk gates, feed subscriptions, dashboard execution and strategy thresholds.

## Scope Guard

This audit records one repaired pipeline defect and known remaining questions. It does not assert the bridge is complete.

## Grill Me Review

The audit is deliberately conservative: fixed-symbol option replay is not dynamic contract certification, and missing authority cannot be hidden as a strategy result.

## Hermes Review

The pipeline must be stage-gated: signal ledger, observed contract universe, expiry, strike, entry quote, premium geometry, replay, costs, reconciliation, controls, WFA, holdout and oracle remain separate contracts.

## GSD Review

The repair added regression coverage for entry quotes captured before the signal. Later work must continue with failing tests before shared repairs.

## QA / Safety Review

No broker, live feed, order, risk, sizing, credential or production strategy path was activated. Outputs remain research-only.

## Acceptance Proof

Acceptance for this checkpoint is the focused option backtest and foundation test suite recorded above, plus the explicit statement that the audit remains incomplete.

## Runtime Proof Required After Merge

No runtime proof is applicable because this PR is a draft research campaign and is not intended to merge into live execution while incomplete.

## What This PR Does Not Prove

It does not prove end-to-end dynamic NIFTY CE/PE replay, complete historical contract authority, positive edge, paper readiness or live readiness.

## Human Approval

Human approval is required before any campaign output is used to alter trading behavior, risk policy, strategy registration or capital allocation.

# Option E2E Pipeline Audit V4

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

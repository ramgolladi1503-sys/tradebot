# Constituent Lead-Lag V1 Proxy Campaign Audit

## Scope

This audit covers the research-only reconstructed NIFTY constituent lead-lag proxy campaign frozen at:

- Index: `NIFTY`
- Provider: `Upstox V3`
- Window: `2024-01-01` through `2025-08-29`
- Campaign root: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v1`
- Raw shared directory inspected: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/upstox_v3/raw`

This remains research-only: `allowed_for_live_execution=false`, `broker_api_called=false`, `is_order_action=false`, `commercial_use_allowed=false`, and `official_weight_gate_passed=false`.

## Prior Claim Invalidation

The earlier positive proxy claim and the later zero-signal diagnosis are invalid as evidence because they were not reproduced from an isolated fetch campaign with row conservation and an independent oracle.

Invalidated classifications:

- `INVALID_UNSUPPORTED_POSITIVE_PROXY_RESULT`
- `INVALID_INCOMPLETE_ZERO_SIGNAL_DIAGNOSIS`
- `INVALID_MIXED_FETCH_CAMPAIGN`

Specifically, the prior `125 eligible sessions`, `160 weighted signals`, `155 unweighted signals`, `160 control signals`, and `PROXY_SUPPORTS_PURCHASING_AUTHORITATIVE_DATA` claims are unsupported. The later `3.5M+ bars`, `5,710 states`, `0 signals`, and `PROXY_DOES_NOT_SUPPORT_PURCHASING_AUTHORITATIVE_DATA` claim is also unsupported for this frozen window. The verified theoretical maximum is `414 completed sessions * 10 decision times = 4,140`, and the actual weighted state count is `4,130`.

## Campaign Inventory

- Raw `.json.gz` files discovered: `2,324`
- Accepted raw files: `1,640`
- Rejected raw files: `684`
- Rejection counts: `outside_frozen_campaign_window=664`, `non_nifty_campaign_symbol=28`
- Files fetched during this repair: `0`
- Fetch requests during this repair: `0`
- Instrument records resolved: `1,640`
- Instrument records unresolved: `0`
- Instrument records ambiguous after NSE cash/index filtering: `0`

The accepted manifest is the only normalizer input:

`/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v1/manifests/accepted_raw_files.json`

## Normalization

- Raw candle rows: `2,532,075`
- Normalized accepted rows: `2,532,066`
- Invalid OHLC quarantined: `9`
- Malformed rows: `0`
- Out-of-window rows: `0`
- Identical duplicates collapsed: `0`
- Conflicting duplicates rejected: `0`
- Row conservation: `PASS`
- Normalized bars path: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v1/normalized/constituent_index_5m.parquet`
- Normalized bars SHA-256: `67fc7fd118f5eaec6470e9b2ccb8b37fa3429a9159ab87b5b8c366c8ad3821b3`
- Normalized date range: `2024-01-01` through `2025-08-29`
- Completed NIFTY sessions: `414`
- Unique symbols: `82`

Row conservation identity:

`2,532,075 = 2,532,066 + 0 + 0 + 9 + 0 + 0`

## Weighted Proxy Evaluation

- Actual weighted state rows: `4,130`
- Theoretical max state rows: `4,140`
- State count bound: `PASS`
- Post-warm-up sessions: `393`
- Low weight-coverage states: `0`
- Weighted signals: `0`
- Weighted evaluable signals: `0`
- Unweighted lane: skipped in this repair run after weighted evidence completed; no unweighted/control economic claim is made.
- Control signals: `0`
- Independent oracle: `PASS`

State reason counts:

```json
{
  "dispersion_too_high": 658,
  "frozen_entry_conditions_not_met": 8,
  "index_already_caught_up": 3166,
  "index_range_already_consumed": 98,
  "insufficient_lead_gap_history": 200
}
```

## Verdict

`NO_QUALIFYING_SIGNALS_UNDER_VALID_PROXY_CONTRACT`

This is a valid zero-signal proxy-contract result for the weighted lane. It is not positive PnL evidence, not negative PnL evidence, and not a truthful basis for `PROXY_DOES_NOT_SUPPORT_PURCHASING_AUTHORITATIVE_DATA`, because no valid weighted signals existed to test out-of-fold performance, delay sensitivity, control lift, or concentration.

## Evidence Paths

- Freeze: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v1/pre_fetch/window_freeze.json`
- Campaign summary: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v1/manifests/campaign_summary.json`
- Normalization report: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v1/normalized/normalization_report.json`
- Bars audit: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v1/reports/bars_audit.json`
- Evaluation summary: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v1/evaluation/summary.json`
- Oracle report: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v1/oracle/oracle_report.json`

## Tests

```bash
pytest -q tests/research/test_reconstructed_weight_proxy.py tests/research/test_constituent_lead_lag.py tests/research/test_unweighted_constituent_breadth.py
```

Result: `18 passed in 5.23s`.

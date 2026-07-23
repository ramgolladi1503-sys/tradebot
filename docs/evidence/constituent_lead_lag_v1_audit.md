# Constituent Lead-Lag V1 Proxy Campaign Audit

## Scope

This audit covers the final research-only reconstructed NIFTY constituent lead-lag proxy campaign repair after head `8ffdc6c5e46366caf4defd70ce4374e9fc8de748`.

- Worktree: `/Users/madhuram/tradebot-constituent-lead-lag-v1`
- Branch: `research/constituent-lead-lag-v1`
- Campaign root: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2`
- Index: `NIFTY`
- Provider: `Upstox V3`
- Window: `2024-01-01` through `2025-08-29`

This remains research-only: `allowed_for_live_execution=false`, `broker_api_called=false`, `is_order_action=false`, `commercial_use_allowed=false`, and `official_weight_gate_passed=false`.

## Head 8ffdc6c5 Invalidation

The prior `NO_QUALIFYING_SIGNALS_UNDER_VALID_PROXY_CONTRACT` verdict at `8ffdc6c5` is invalidated as:

`INVALID_INCOMPLETE_PROXY_CONTRACT`

External invalidation artifact:

`/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/invalid_8ff_proxy_contract/INVALIDATION.json`

## Proxy Provenance

- Source manifest: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/reconstructed_nifty50_weights/download_manifest.json`
- Source manifest SHA-256: recorded in `pre_fetch/window_freeze.json`
- Dataset: `Historical Nifty 50 Constituent Weights`
- DOI: `10.6084/m9.figshare.30217915`
- License: `CC BY-NC-SA 4.0`
- Raw weights: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/reconstructed_nifty50_weights/raw/weights.csv`
- Raw weights SHA-256: `3a3441a997b64a54363b38ebc02807e82cc0e0affd2efda147d1b7758a0b10cb`
- Normalized weights: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/normalized/point_in_time_weights_proxy.global_intervals.csv`
- Normalized weights SHA-256: `aa403401627f0fb433026f23531b59d61b07c499b9fe6c9095eb04ca35c2c416`
- Latest snapshot derived from normalized/source data: `2025-08-31`

Membership intervals are derived by global index snapshot. A row from snapshot `D` is active from `D` through one day before the next global NIFTY proxy snapshot, not until that constituent next appears.

## Campaign Inventory

- Raw file records discovered: `2,324`
- Raw file records accepted: `1,640`
- Raw file records rejected: `684`
- Original fetch manifest: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/upstox_v3/manifest.json`
- Original fetch manifest SHA-256: `1c439c6abf492e1951bf3dd583b1ee6e54362c0b0a93901862ed4cbea2b22e8e`
- Filename-only authority check: `PASS`; files without authoritative ownership are rejected.
- Unique required tickers: `82`
- Unique resolved trading symbols: `82`
- Unique instrument keys: `82`
- Unique ISINs: `81`
- Unresolved unique tickers: `0`
- Ambiguous unique tickers: `0`
- Fetch requests during this repair: `0`
- Files fetched during this repair: `0`

## Normalization

- Raw candle rows: `2,532,075`
- Normalized accepted rows: `2,532,066`
- Invalid OHLC quarantined: `9`
- Malformed rows: `0`
- Out-of-window rows: `0`
- Identical duplicates collapsed: `0`
- Conflicting duplicates rejected: `0`
- Row conservation: `PASS`
- Normalized bars path: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/normalized/constituent_index_5m.parquet`
- Normalized bars SHA-256: `ae9645a83cb555899145e04ebe5a961fd130df25cba88a8fc8fd43b986bbfad0`
- Normalized date range: `2024-01-01` through `2025-08-29`
- Unique symbols: `82`

## Session Grid

Session completion requires the full regular NIFTY 5-minute grid from `09:15` through `15:25` Asia/Kolkata and all frozen decision cutoffs.

- NIFTY sessions present: `414`
- Completed sessions: `411`
- Rejected partial sessions: `3`
- Rejected partial session dates: `2024-03-02`, `2024-05-18`, `2024-11-01`
- Eligible sessions: `411`
- Post-warm-up sessions: `391`
- Theoretical max state rows: `4,110`
- Actual weighted state rows: `4,110`
- Missing state explanation: `0` missing after completed-session filtering; the prior unfiltered runner produced `4,130` states, while v2 removes `20` states attributable to the three rejected partial sessions before evaluation.

## Coverage

- Count coverage min: `0.94`
- Count coverage median: `0.96`
- Weight coverage min: `0.9632108`
- Weight coverage median: `0.9712971`
- Low count-coverage states: `0`
- Low weight-coverage states: `0`
- Both-gates pass rate: `1.0`

## Weighted Lane

State reason counts:

```json
{
  "dispersion_too_high": 651,
  "frozen_entry_conditions_not_met": 8,
  "index_already_caught_up": 3153,
  "index_range_already_consumed": 98,
  "insufficient_lead_gap_history": 200
}
```

- Weighted signals: `0`
- Weighted evaluable signals: `0`
- Control result: `NOT_APPLICABLE_ZERO_SIGNALS`
- Delay result: `NOT_APPLICABLE_ZERO_SIGNALS`
- Concentration result: `NOT_APPLICABLE_ZERO_SIGNALS`
- Chronological folds: no weighted folds because weighted signals are zero.

## Unweighted Lane

State reason counts:

```json
{
  "dispersion_too_high": 642,
  "frozen_unweighted_entry_conditions_not_met": 48,
  "index_already_caught_up": 2632,
  "index_range_already_consumed": 587,
  "insufficient_lead_gap_history": 200,
  "unweighted_constituents_lead_index_down": 1
}
```

- Unweighted state rows: `4,110`
- Unweighted signals: `1`
- Unweighted evaluable signals: `1`
- Unweighted net mean bps: `2.5000000000013944`

The unweighted lane is reported for completeness. The final taxonomy below is based on the weighted proxy contract specified for the zero-signal verdict.

## Oracle

Independent oracle verdict: `PASS`

Oracle checks:

- bars/hash/summary reconciliation: `PASS`
- reason-count sum: `PASS`
- weighted signal count: `PASS`
- unweighted signal count: `PASS`
- coverage row count and gate pass rate: `PASS`
- state-count bound: `PASS`

## Final Decision

`NO_QUALIFYING_SIGNALS_UNDER_VALID_PROXY_CONTRACT`

This is a valid weighted zero-signal proxy-contract result. It is not positive PnL evidence and not negative PnL evidence. It does not support `PROXY_DOES_NOT_SUPPORT_PURCHASING_AUTHORITATIVE_DATA`, because there are no weighted signals for OOF/control/delay/concentration economic testing.

## Evidence Paths

- Invalidation: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/invalid_8ff_proxy_contract/INVALIDATION.json`
- Freeze: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/pre_fetch/window_freeze.json`
- Campaign summary: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/manifests/campaign_summary.json`
- Ticker resolution: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/manifests/ticker_resolution.csv`
- Normalization report: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/normalized/normalization_report.json`
- Session grid: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/reports/session_grid.parquet`
- Coverage summary: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/reports/membership_coverage_summary.json`
- Evaluation summary: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/evaluation/summary.json`
- Oracle report: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/oracle/oracle_report.json`

## Tests

```bash
pytest -q tests/research/test_reconstructed_weight_proxy.py tests/research/test_constituent_lead_lag.py tests/research/test_unweighted_constituent_breadth.py
```

Latest result: `22 passed`.

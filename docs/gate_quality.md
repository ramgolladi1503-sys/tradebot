# Gate Quality And Reject-Shadow Evaluation

This module set provides post-decision auditability for blocked or non-executable
trade candidates.

## What Is Stored

- `candidate_decision_events`: one row per candidate decision trace.
- `rejected_trades_shadow`: shadow outcomes queue for blocked/non-executable candidates.
- `price_trace`: append-only symbol price points used by evaluator.
- `gate_quality_daily`: daily gate quality aggregates.

All tables are created lazily by `core.reject_shadow.ensure_tables`.

## Core Runtime Behavior

- Every blocked candidate and every retained suggestion writes a structured
  decision event (`record_candidate_decision`).
- If a candidate is blocked or marked `execution_allowed=False`, it is inserted
  into `rejected_trades_shadow` with `shadow_status='PENDING'`.
- `core.market_data.fetch_live_market_data` writes price points into `price_trace`
  via `record_price_trace`.

## Evaluate Shadow Outcomes

```bash
python -m core.reject_shadow --mode evaluate --date 2026-02-24
```

Resolution rules:

- `WIN`: target touched before stop.
- `LOSS`: stop touched before target.
- `TIMEOUT`: no touch until timeout horizon (`REJECT_SHADOW_TIMEOUT_MIN`) or day-end.

## Generate Gate Quality Report

```bash
python -m core.gate_quality_report --date 2026-02-24
```

Outputs:

- SQLite upserts into `gate_quality_daily`
- JSON artifact:
  - `${REPORTS_ROOT}/gate_quality_YYYYMMDD.json`
- Console summary with top gates by missed expectancy.

## Verdict Rules

- `CRITICAL_OVERBLOCK`: `win_rate > 0.40` and `avg_best_rr > 1.5`
- `TOO_STRICT`: `win_rate > 0.25`
- `ACCEPTABLE`: `win_rate < 0.10`
- `REVIEW`: otherwise

## Config Keys

- `TRADING_MODE` (`LIVE|PAPER|SIM`)
- `REJECT_SHADOW_TIMEOUT_MIN`
- `REJECT_SHADOW_BATCH_LIMIT`
- `REJECT_SHADOW_CANDIDATE_BUCKET_SEC`
- `REJECT_SHADOW_DEFAULT_RR`
- `PREMIUM_BAND_PERCENTILE_LOW`
- `PREMIUM_BAND_PERCENTILE_HIGH`
- `PREMIUM_BAND_ATM_MONEYNESS_MAX`
- `PREMIUM_BAND_MIN_ROWS`
- `PREMIUM_BAND_MIN_VOLUME`


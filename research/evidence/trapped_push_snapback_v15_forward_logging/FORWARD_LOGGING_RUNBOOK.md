# Forward Logging Runbook — H1 Trapped Push Snapback

## Purpose
This runbook defines the governed procedure for running forward prospective observation logging for `H1_TRAPPED_PUSH_SNAPBACK` without placing, modifying, or cancelling any broker orders.

## Candidate Scope
- **Candidate ID**: `H1_TRAPPED_PUSH_SNAPBACK`
- **Support Label**: `HISTORICAL_OOS_SUPPORTED_OPENING_MICRO_PATTERN_EXECUTION_UNVERIFIED`
- **Scope Window**: `09:15-11:30 IST` (Opening Window only)
- **Bar Granularity**: Completed 5-minute OHLC bars
- **Target Measurement**: NIFTY 6-bar (30-minute) short return

## Governance Authority Flags (Strict Read-Only)
```json
{
  "broker_write_authority": false,
  "order_authority": false,
  "paper_authorized": false,
  "live_authorized": false,
  "edge_claimed": false,
  "execution_viable": false,
  "prospective_supported": false,
  "structural_edge_certified": false
}
```

## Required Inputs & Execution Command
```bash
python3 scripts/research/hypothesis_factory/run_trapped_push_snapback_v14_prospective_observer.py \
  --mode historical_replay \
  --input-bars <path_to_completed_bars_csv> \
  --output-root research/evidence/trapped_push_snapback_v15_forward_logging/runs \
  --run-id V15_SESSION_<YYYYMMDD> \
  --candidate-id H1_TRAPPED_PUSH_SNAPBACK \
  --opening-start 09:15 \
  --opening-end 11:30 \
  --evidence-commit <authoritative_latest_commit> \
  --registry-commit b57197b5643b0e99087dbfac091eb9a2054a5e1b
```

## Operating Procedures
1. **Clock Rule**: Forward observation logging for a given session MUST occur after completed 5-minute bars are available for that session.
2. **Opening Window Check**: The script automatically filters bars to `09:15-11:30 IST`. Bars outside this window are recorded in `out_of_scope_bar_log.jsonl`.
3. **Post-Session Procedure**: Once 6 future bars exist following a trigger, the script computes outcome metrics in `post_event_return_log.jsonl` with `outcome_status: OUTCOME_AVAILABLE`. If < 6 future bars exist, it marks `OUTCOME_PENDING_INSUFFICIENT_FUTURE_BARS`.
4. **Prospective Evaluation Gate**:
   - `minimum_sessions >= 20`
   - `minimum_events >= 20`
   - `minimum_cost_adj_expectancy_bps >= 5.0`
   - `minimum_win_rate >= 0.55`
   - `zero authority violations`

## Forbidden Actions
- NEVER pass `--order-authority` or `--broker-write-authority`.
- NEVER attempt to submit orders to Kite, Upstox, or any broker API.
- NEVER claim prospective support or live readiness before 20 prospective sessions/events complete under governance.

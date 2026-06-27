# Outcome Evidence Schema

The `OutcomeEvidenceStore` produces JSONL outputs representing the execution evidence for strategy candidates. This schema defines the structure of each record in the output JSONL.

## OutcomeEvidenceRecord

Each JSON line represents an `OutcomeEvidenceRecord` with the following schema:

```json
{
  "run_id": "string",
  "candidate_id": "string",
  "strategy_id": "string",
  "input_source": "string",
  "evidence_quality": "string (COMPLETE, PARTIAL, INSUFFICIENT, UNUSABLE)",
  "outcome_status": "string (TARGET_HIT, STOP_HIT, AMBIGUOUS_BOTH_HIT, TIME_STOP, NO_TRACE_DATA, INSUFFICIENT_CANDIDATE_FIELDS, OPEN_AT_END, PENDING)",
  "exit_reason": "string (TARGET, STOP, TIME_STOP, END_OF_WINDOW, UNKNOWN)",
  "mfe_mae": {
    "mfe_points": "float",
    "mae_points": "float",
    "mfe_r": "float",
    "mae_r": "float",
    "realized_r": "float",
    "max_drawdown": "float",
    "time_to_mfe": "float",
    "time_to_mae": "float",
    "hold_duration": "float"
  },
  "cost_breakdown": {
    "brokerage": "float",
    "stt": "float",
    "exchange_tx": "float",
    "sebi": "float",
    "stamp_duty": "float",
    "gst": "float",
    "slippage": "float",
    "spread_cost": "float",
    "total_cost": "float",
    "lot_size": "int",
    "status": "string (COMPLETE, ESTIMATED, INCOMPLETE)"
  },
  "gross_pnl": "float",
  "net_pnl": "float",
  "regime_context": {
    "trend": "string | null",
    "range_status": "string | null",
    "entropy": "float | null",
    "volatility": "float | null",
    "iv_bucket": "string | null",
    "session_bucket": "string | null",
    "is_expiry_day": "boolean | null",
    "liquidity_bucket": "string | null",
    "spread_bucket": "string | null",
    "mip_event_context": "string | null"
  },
  "simulation": {
    "entry_fill": "float",
    "exit_fill": "float",
    "spread_impact": "float",
    "slippage_impact": "float",
    "delayed_entry": "boolean",
    "delayed_exit": "boolean",
    "is_hypothetical_rejected": "boolean"
  },
  "warnings": ["string"],
  "created_timestamp": "float"
}
```

## Nested Structures
- **mfe_mae**: Can be null if the `outcome_status` is `NO_TRACE_DATA` or `INSUFFICIENT_CANDIDATE_FIELDS`.
- **regime_context**: Fields can be null if no regime snapshot is available for the given timeframe.
- **simulation**: Contains the details on execution eligibility, including `is_hypothetical_rejected=True` if the candidate was generated but rejected by execution risk engines.

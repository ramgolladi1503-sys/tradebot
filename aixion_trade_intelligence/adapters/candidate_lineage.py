from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ..contracts import CanonicalEvent, parse_timestamp


def _text(value: Any) -> str:
    return str(value or "").strip()


def candidate_lineage_event_type(row: Mapping[str, Any]) -> str:
    stage = _text(row.get("stage")).lower()
    status = _text(row.get("stage_status") or row.get("status")).lower()
    if status == "blocked":
        return "CANDIDATE_BLOCKED"
    if status == "selected" or stage in {"ranking", "ranked", "top_opportunity"}:
        return "CANDIDATE_RANKED"
    if stage in {"generated", "strategy", "strategy_generation"}:
        return "SIGNAL_GENERATED"
    if stage in {"approval", "manual_approval"}:
        return "APPROVAL_DECIDED" if _text(row.get("decision")) else "APPROVAL_REQUESTED"
    return "CANDIDATE_CREATED"


def adapt_candidate_lineage_row(
    row: Mapping[str, Any],
    *,
    session_id: str,
    producer_sequence: int,
    observed_at: datetime | None = None,
) -> CanonicalEvent:
    now = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    timestamp = row.get("timestamp")
    if timestamp:
        event_time = parse_timestamp(timestamp, field_name="timestamp")
    elif row.get("ts_epoch") is not None:
        event_time = datetime.fromtimestamp(float(row["ts_epoch"]), tz=timezone.utc)
    else:
        event_time = now
    available_time = max(event_time, now)
    metadata = dict(row.get("metadata")) if isinstance(row.get("metadata"), Mapping) else {}
    outcome_contract = metadata.get("outcome_contract")
    payload = {
        "stage": _text(row.get("stage")),
        "stage_status": _text(row.get("stage_status") or row.get("status")),
        "direction": _text(row.get("direction") or metadata.get("direction")),
        "underlying_instrument": _text(
            row.get("underlying_instrument") or metadata.get("underlying_instrument") or row.get("underlying")
        ),
        "selected_option_instrument": _text(
            row.get("selected_option_instrument")
            or metadata.get("selected_option_instrument")
            or row.get("instrument_key")
        ),
        "ranking_bucket": _text(row.get("ranking_bucket")),
        "score": row.get("score"),
        "final_score": row.get("final_score"),
        "setup_score": row.get("setup_score"),
        "regime": _text(row.get("regime")),
        "quote_age_sec": row.get("quote_age_sec"),
        "option_ltp_age_sec": row.get("option_ltp_age_sec"),
        "underlying_tick_age_sec": row.get("underlying_tick_age_sec"),
        "spread": row.get("spread"),
        "spread_pct": row.get("spread_pct"),
        "liquidity_ok": row.get("liquidity_ok"),
        "depth_available": row.get("depth_available"),
        "fallback_used": bool(row.get("fallback_used")),
        "recovered_fallback": bool(row.get("recovered_fallback")),
        "stale_quote": bool(row.get("stale_quote")),
        "advisory": bool(row.get("advisory")),
        "degraded": bool(row.get("degraded")),
        "reason": _text(row.get("block_reason") or row.get("selection_reason")),
        "blockers": list(row.get("downgrade_reasons") or []),
        "source_lineage_row": dict(row),
    }
    if isinstance(outcome_contract, Mapping):
        payload["outcome_contract"] = dict(outcome_contract)
    return CanonicalEvent(
        event_type=candidate_lineage_event_type(row),
        session_id=session_id,
        run_id=session_id,
        cycle_id=_text(row.get("cycle_id")),
        trace_id=session_id,
        producer_id="tradebot-candidate-lineage",
        producer_sequence=producer_sequence,
        source_component="core.candidate_lineage_ledger",
        source_provider="TRADEBOT_RUNTIME",
        event_time=event_time,
        source_time=event_time,
        receive_time=available_time,
        available_time=available_time,
        parse_time=available_time,
        persist_time=available_time,
        instrument_key=_text(
            row.get("instrument_key")
            or metadata.get("instrument_key")
            or metadata.get("selected_option_instrument")
            or metadata.get("option_instrument")
        ),
        underlying=_text(row.get("underlying") or row.get("symbol")),
        strategy_id=_text(row.get("strategy_name") or row.get("strategy_id")),
        strategy_version=_text(row.get("strategy_version") or metadata.get("strategy_version")),
        candidate_id=_text(row.get("candidate_id") or row.get("trade_id") or row.get("instrument_id")),
        data_quality_state=(
            "DEGRADED" if any(bool(row.get(flag)) for flag in ("fallback_used", "recovered_fallback", "stale_quote", "advisory", "degraded"))
            else "OBSERVED"
        ),
        authority_class="TRADEBOT_CANDIDATE_LINEAGE",
        payload=payload,
    )

"""Asynchronous / Session-safe Outcome Collector for Trade Truth.

Computes forward price, MFE, and MAE across horizons (+1m, +3m, +5m, +10m, +15m, +30m)
without mutating historical decision records. Emits append-only OUTCOME_AMENDMENT records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from core.trade_truth.models import TradeTruthRecord
from core.trade_truth.record_builder import build_trade_truth_record
from core.trade_truth.store import TruthStore

DEFAULT_HORIZON_SECONDS = {
    "+1m": 60,
    "+3m": 180,
    "+5m": 300,
    "+10m": 600,
    "+15m": 900,
    "+30m": 1800,
}


@dataclass(frozen=True)
class PricePoint:
    timestamp_epoch: float
    ltp: float
    bid: float | None = None
    ask: float | None = None


def compute_horizons_mfe_mae(
    *,
    decision_epoch: float,
    entry_price: float,
    direction: str,
    price_series: Sequence[PricePoint],
    horizons_sec: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Compute MFE and MAE across forward horizons for a trade decision."""
    h_map = dict(horizons_sec or DEFAULT_HORIZON_SECONDS)
    sorted_series = sorted(price_series, key=lambda p: p.timestamp_epoch)

    # Filter forward prices occurring after decision
    forward = [p for p in sorted_series if p.timestamp_epoch >= decision_epoch]
    if not forward:
        return {
            "status": "NO_OBSERVATIONS",
            "horizons": {},
            "mfe_abs": 0.0,
            "mae_abs": 0.0,
        }

    is_bullish = direction.upper() in {"BUY", "BUY_CALL", "LONG"}
    mfe_abs = 0.0
    mae_abs = 0.0
    horizons_res = {}

    for label, sec in h_map.items():
        cutoff = decision_epoch + sec
        window = [p for p in forward if p.timestamp_epoch <= cutoff]
        if not window:
            continue

        prices = [p.ltp for p in window]
        if is_bullish:
            max_p = max(prices)
            min_p = min(prices)
            h_mfe = max(0.0, max_p - entry_price)
            h_mae = max(0.0, entry_price - min_p)
        else:
            max_p = max(prices)
            min_p = min(prices)
            h_mfe = max(0.0, entry_price - min_p)
            h_mae = max(0.0, max_p - entry_price)

        last_p = window[-1].ltp
        horizons_res[label] = {
            "forward_price": last_p,
            "mfe": h_mfe,
            "mae": h_mae,
            "sample_count": len(window),
        }
        if h_mfe > mfe_abs:
            mfe_abs = h_mfe
        if h_mae > mae_abs:
            mae_abs = h_mae

    return {
        "status": "OBSERVED",
        "horizons": horizons_res,
        "mfe_abs": mfe_abs,
        "mae_abs": mae_abs,
    }


def attach_outcome_amendment(
    original_record: Mapping[str, Any],
    price_series: Sequence[PricePoint],
    store: TruthStore,
) -> TradeTruthRecord:
    """Create and persist an append-only OUTCOME_AMENDMENT for an existing truth record."""
    ident = original_record.get("identity") or {}
    tim = original_record.get("timing") or {}
    dec = original_record.get("decision") or {}
    exc = original_record.get("execution") or {}

    decision_epoch = tim.get("decision_timestamp_epoch") or 0.0
    entry_price = float(exc.get("intended_entry") or exc.get("theoretical_executable_price") or 0.0)
    direction = str(exc.get("intended_action") or "BUY_CALL")

    outcome_calc = compute_horizons_mfe_mae(
        decision_epoch=decision_epoch,
        entry_price=entry_price,
        direction=direction,
        price_series=price_series,
    )

    amended_record = build_trade_truth_record(
        trace_id=ident.get("trace_id", "UNKNOWN"),
        session_id=ident.get("session_id", "UNKNOWN"),
        candidate=ident,
        market_snapshot=original_record.get("market") or {},
        analytical_context=original_record.get("analytical") or {},
        decision_context=dec,
        execution_context=exc,
        outcome_context=outcome_calc,
        timing_context=tim,
        provenance_context=original_record.get("provenance") or {},
        sequence_number=store.next_sequence_number,
        previous_record_hash=store.last_record_hash,
        record_type="OUTCOME_AMENDMENT",
        parent_truth_record_id=ident.get("truth_record_id"),
    )

    store.write_record(amended_record)
    return amended_record

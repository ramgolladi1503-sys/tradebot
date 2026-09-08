from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Any

import pandas as pd

from research.option_e2e_recertification_v4.option_candle_backtest_v1.models import (
    CandleBacktestResult,
)

from .campaign import CompressionCampaignResult
from .signal_ledger import CompressionSignalLedgerResult


_IDENTITY_FIELDS = (
    "strategy_id",
    "strategy_version",
    "underlying",
    "underlying_price",
    "direction",
    "candidate_direction",
    "signal_ts",
    "feature_cutoff_ts",
    "earliest_entry_ts",
    "session_date",
    "raw_strategy_score",
    "confidence_score",
    "rank_score",
    "params_hash",
    "adapter_version",
    "timestamp_semantics",
    "vwap_authority",
    "range_width_pct",
    "atr_short",
    "atr_long",
    "breakout_level",
    "breakout_distance_pct",
)


def _normalise(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (dict, list, tuple, bool, int, float, str)):
        return value
    return str(value)


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def feature_identity_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        field: _normalise(row.get(field))
        for field in _IDENTITY_FIELDS
    }


def feature_input_hash(row: dict[str, Any]) -> str:
    return _canonical_hash(feature_identity_record(row))


def _rebind_signal_frame(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, str]]:
    signals = frame.copy()
    if signals.empty:
        if "feature_input_hash" not in signals.columns:
            signals["feature_input_hash"] = pd.Series(dtype=str)
        return signals, {}

    records = signals.to_dict("records")
    hashes = [feature_input_hash(row) for row in records]
    new_ids = [digest[:24] for digest in hashes]
    old_ids = signals.get("signal_id", pd.Series([""] * len(signals))).astype(str)
    mapping = {
        old: new
        for old, new in zip(old_ids.tolist(), new_ids)
        if old
    }
    signals["feature_input_hash"] = hashes
    signals["signal_id"] = new_ids
    signals["signal_identity_version"] = "causal_feature_identity_v1"
    if signals["signal_id"].duplicated().any():
        raise ValueError("duplicate_causal_signal_identity")
    return signals, mapping


def rebind_ledger_identity(
    result: CompressionSignalLedgerResult,
) -> tuple[CompressionSignalLedgerResult, dict[str, str]]:
    signals, mapping = _rebind_signal_frame(result.signals)
    summary = dict(result.summary)
    summary["signal_identity_version"] = "causal_feature_identity_v1"
    summary["source_dataset_hash_role"] = "provenance_only"
    summary["ledger_semantic_hash"] = _canonical_hash(
        signals.to_dict("records")
    )
    return replace(result, signals=signals, summary=summary), mapping


def _rebind_backtest_result(
    result: CandleBacktestResult | None,
    mapping: dict[str, str],
) -> CandleBacktestResult | None:
    if result is None:
        return None
    trades = [
        replace(trade, signal_id=mapping.get(trade.signal_id, trade.signal_id))
        for trade in result.trades
    ]
    rejections = [
        {
            **row,
            "signal_id": mapping.get(
                str(row.get("signal_id") or ""),
                row.get("signal_id"),
            ),
        }
        for row in result.rejections
    ]
    selections = [
        {
            **row,
            "signal_id": mapping.get(
                str(row.get("signal_id") or ""),
                row.get("signal_id"),
            ),
        }
        for row in result.selections
    ]
    return replace(
        result,
        trades=trades,
        rejections=rejections,
        selections=selections,
    )


def rebind_campaign_identity(
    result: CompressionCampaignResult,
) -> CompressionCampaignResult:
    ledger, mapping = rebind_ledger_identity(result.ledger)
    partition_signals = result.partition_signals.copy()
    if not partition_signals.empty:
        partition_signals["signal_id"] = partition_signals["signal_id"].astype(
            str
        ).map(lambda value: mapping.get(value, value))
        feature_by_id = dict(
            zip(ledger.signals["signal_id"], ledger.signals["feature_input_hash"])
        )
        partition_signals["feature_input_hash"] = partition_signals[
            "signal_id"
        ].map(feature_by_id)
        partition_signals["signal_identity_version"] = (
            "causal_feature_identity_v1"
        )

    base_result = _rebind_backtest_result(result.base_result, mapping)
    summary = dict(result.summary)
    summary["ledger_semantic_hash"] = ledger.summary["ledger_semantic_hash"]
    summary["signal_identity_version"] = "causal_feature_identity_v1"
    summary["source_dataset_hash_role"] = "provenance_only"
    summary_without_hash = dict(summary)
    summary_without_hash.pop("semantic_hash", None)
    summary["semantic_hash"] = _canonical_hash(summary_without_hash)
    return replace(
        result,
        ledger=ledger,
        partition_signals=partition_signals,
        base_result=base_result,
        summary=summary,
    )


__all__ = [
    "feature_identity_record",
    "feature_input_hash",
    "rebind_campaign_identity",
    "rebind_ledger_identity",
]

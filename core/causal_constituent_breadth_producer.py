"""Causal completed-bar constituent breadth producer for shadow strategy input.

The producer is read-only and fail-closed. It never subscribes to feeds, calls a
broker, guesses thresholds, or uses an incomplete bar. Runtime/replay callers
provide completed constituent and index bars plus immutable discovery thresholds.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

CONSTITUENT_BAR_KEYS = ("completed_constituent_bars", "constituent_bar_history")
INDEX_BAR_KEYS = ("completed_index_bars", "index_bar_history")
THRESHOLD_KEY = "market_event_graph_frozen_thresholds"
MIN_CONSTITUENT_COVERAGE = 40
MAX_BAR_AGE_SEC = 420.0


def enrich_metadata_with_constituent_breadth(
    metadata: Mapping[str, Any] | None,
    *,
    context_ts: float | None = None,
) -> dict[str, Any]:
    """Return copied metadata with causal completed breadth snapshots attached."""

    out = dict(metadata or {})
    result = build_completed_constituent_breadth_snapshots(out, context_ts=context_ts)
    out["constituent_breadth_producer_status"] = result["status"]
    out["constituent_breadth_producer_reason"] = result["reason"]
    out["constituent_breadth_producer_metrics"] = result["metrics"]
    if result["snapshots"]:
        out["completed_constituent_breadth_snapshots"] = result["snapshots"]
    else:
        out.pop("completed_constituent_breadth_snapshots", None)
    return out


def build_completed_constituent_breadth_snapshots(
    payload: Mapping[str, Any] | None,
    *,
    context_ts: float | None = None,
) -> dict[str, Any]:
    """Build chronological labelled snapshots from synchronized completed bars."""

    if not isinstance(payload, Mapping):
        return _result("MISSING_OR_INVALID", "payload_not_mapping")
    thresholds = _thresholds(payload.get(THRESHOLD_KEY))
    if thresholds is None:
        return _result("MISSING_THRESHOLDS", "frozen_thresholds_missing_or_invalid")
    constituent_rows = _first_sequence(payload, CONSTITUENT_BAR_KEYS)
    index_rows = _first_sequence(payload, INDEX_BAR_KEYS)
    if constituent_rows is None or index_rows is None:
        return _result("MISSING_BARS", "completed_constituent_or_index_bars_missing")

    grouped: dict[float, list[dict[str, Any]]] = defaultdict(list)
    for raw in constituent_rows:
        row = _bar(raw)
        if row is not None:
            grouped[row["ts_epoch"]].append(row)
    index_by_ts = {row["ts_epoch"]: row for raw in index_rows if (row := _bar(raw)) is not None}

    snapshots: list[dict[str, Any]] = []
    rejected_coverage = 0
    rejected_stale = 0
    for ts_epoch in sorted(set(grouped).intersection(index_by_ts)):
        rows = grouped[ts_epoch]
        unique = {row["symbol"]: row for row in rows}
        if len(unique) < MIN_CONSTITUENT_COVERAGE:
            rejected_coverage += 1
            continue
        if context_ts is not None and not _fresh(ts_epoch, context_ts):
            rejected_stale += 1
            continue
        returns = [(row["close"] / row["previous_close"]) - 1.0 for row in unique.values()]
        breadth_down_1 = sum(value < 0.0 for value in returns) / len(returns)
        breadth_mean_ret1 = sum(returns) / len(returns)
        index_row = index_by_ts[ts_epoch]
        index_ret1 = (index_row["close"] / index_row["previous_close"]) - 1.0
        divergence = index_ret1 - breadth_mean_ret1
        labels = _labels(breadth_down_1, divergence, thresholds)
        for label in labels:
            snapshots.append(
                {
                    "event_label": label,
                    "ts_epoch": ts_epoch,
                    "completed": True,
                    "breadth_down_1": breadth_down_1,
                    "breadth_mean_ret1": breadth_mean_ret1,
                    "index_ret1": index_ret1,
                    "index_breadth_divergence": divergence,
                    "participation_count": len(unique),
                    "source_bar_end_epoch": ts_epoch,
                    "threshold_version": thresholds["version"],
                }
            )

    status = "READY" if snapshots else "NO_LABELLED_EVENTS"
    reason = "completed_labelled_snapshots_built" if snapshots else "no_completed_bar_crossed_frozen_thresholds"
    return _result(
        status,
        reason,
        snapshots=snapshots,
        metrics={
            "constituent_rows": len(constituent_rows),
            "index_rows": len(index_rows),
            "synchronized_timestamps": len(set(grouped).intersection(index_by_ts)),
            "labelled_snapshot_count": len(snapshots),
            "rejected_low_coverage": rejected_coverage,
            "rejected_stale": rejected_stale,
            "minimum_constituent_coverage": MIN_CONSTITUENT_COVERAGE,
        },
    )


def _labels(breadth_down: float, divergence: float, thresholds: dict[str, Any]) -> tuple[str, ...]:
    labels: list[str] = []
    if breadth_down >= thresholds["breadth_down_high"]:
        labels.append("breadth_down_1:HIGH")
    if divergence <= thresholds["index_breadth_divergence_low"]:
        labels.append("index_breadth_divergence:LOW")
    if breadth_down <= thresholds["breadth_down_low"]:
        labels.append("breadth_down_1:LOW")
    return tuple(labels)


def _thresholds(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        high = float(value["breadth_down_high"])
        low = float(value["breadth_down_low"])
        divergence = float(value["index_breadth_divergence_low"])
    except (KeyError, TypeError, ValueError):
        return None
    version = str(value.get("version") or "").strip()
    if not version or not (0.0 <= low < high <= 1.0):
        return None
    return {
        "breadth_down_high": high,
        "breadth_down_low": low,
        "index_breadth_divergence_low": divergence,
        "version": version,
    }


def _bar(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    if value.get("completed") is not True and value.get("is_completed") is not True:
        return None
    try:
        ts_epoch = float(value["ts_epoch"])
        close = float(value["close"])
        previous_close = float(value["previous_close"])
    except (KeyError, TypeError, ValueError):
        return None
    symbol = str(value.get("symbol") or value.get("trading_symbol") or "").strip().upper()
    if not symbol or ts_epoch <= 0 or close <= 0 or previous_close <= 0:
        return None
    return {"symbol": symbol, "ts_epoch": ts_epoch, "close": close, "previous_close": previous_close}


def _first_sequence(payload: Mapping[str, Any], keys: Sequence[str]) -> Sequence[Any] | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (list, tuple)):
            return value
    return None


def _fresh(event_ts: float, context_ts: float) -> bool:
    age = float(context_ts) - event_ts
    return 0.0 <= age <= MAX_BAR_AGE_SEC


def _result(
    status: str,
    reason: str,
    *,
    snapshots: list[dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "snapshots": list(snapshots or []),
        "metrics": dict(metrics or {}),
        "is_order_action": False,
        "broker_api_called": False,
    }


__all__ = [
    "CONSTITUENT_BAR_KEYS",
    "INDEX_BAR_KEYS",
    "MAX_BAR_AGE_SEC",
    "MIN_CONSTITUENT_COVERAGE",
    "THRESHOLD_KEY",
    "build_completed_constituent_breadth_snapshots",
    "enrich_metadata_with_constituent_breadth",
]

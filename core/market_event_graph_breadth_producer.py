"""Causal producer for completed constituent-breadth event snapshots.

The producer is read-only and fail-closed. It consumes completed index/constituent
return snapshots plus frozen thresholds supplied by research evidence. It never
fetches data, tunes thresholds, calls a broker, or creates an order action.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

_REQUIRED_THRESHOLD_KEYS = (
    "breadth_high",
    "breadth_low",
    "divergence_low",
)


def produce_completed_constituent_breadth_snapshots(
    metadata: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build ordered labelled events from completed bars, or return [] on invalid input."""

    if not isinstance(metadata, Mapping):
        return []
    bars = metadata.get("completed_constituent_bars")
    thresholds = metadata.get("market_event_graph_thresholds")
    if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes)):
        return []
    if not isinstance(thresholds, Mapping):
        return []

    parsed_thresholds = _parse_thresholds(thresholds)
    if parsed_thresholds is None:
        return []
    breadth_high, breadth_low, divergence_low, min_constituents = parsed_thresholds

    rows: list[dict[str, Any]] = []
    for raw in bars:
        row = _compute_row(raw, min_constituents=min_constituents)
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda item: item["ts_epoch"])
    if not rows:
        return []

    events: list[dict[str, Any]] = []
    state = "WAIT_HIGH"
    for row in rows:
        breadth = row["breadth_down_1"]
        divergence = row["index_breadth_divergence"]
        label: str | None = None
        if state == "WAIT_HIGH" and breadth >= breadth_high:
            label = "breadth_down_1:HIGH"
            state = "WAIT_DIVERGENCE"
        elif state == "WAIT_DIVERGENCE" and divergence <= divergence_low:
            label = "index_breadth_divergence:LOW"
            state = "WAIT_LOW"
        elif state == "WAIT_LOW" and breadth <= breadth_low:
            label = "breadth_down_1:LOW"
            state = "WAIT_HIGH"

        if label is not None:
            events.append({**row, "event_label": label, "completed": True})

    return events


def attach_completed_constituent_breadth_snapshots(
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Copy metadata and attach producer output plus explicit status evidence."""

    out = dict(metadata or {})
    events = produce_completed_constituent_breadth_snapshots(out)
    if events:
        out["completed_constituent_breadth_snapshots"] = events
        out["constituent_breadth_producer_status"] = "READY"
        out["constituent_breadth_event_count"] = len(events)
    else:
        out.pop("completed_constituent_breadth_snapshots", None)
        out["constituent_breadth_producer_status"] = "MISSING_OR_INVALID"
        out["constituent_breadth_event_count"] = 0
    return out


def _parse_thresholds(values: Mapping[str, Any]) -> tuple[float, float, float, int] | None:
    try:
        parsed = {key: float(values[key]) for key in _REQUIRED_THRESHOLD_KEYS}
        min_constituents = int(values.get("min_constituents", 40))
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in parsed.values()):
        return None
    if not 0.0 <= parsed["breadth_low"] < parsed["breadth_high"] <= 1.0:
        return None
    if min_constituents < 1:
        return None
    return (
        parsed["breadth_high"],
        parsed["breadth_low"],
        parsed["divergence_low"],
        min_constituents,
    )


def _compute_row(raw: Any, *, min_constituents: int) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    if raw.get("completed") is False or raw.get("is_completed") is False:
        return None
    try:
        ts_epoch = float(raw["ts_epoch"])
        index_ret1 = float(raw["index_ret1"])
    except (KeyError, TypeError, ValueError):
        return None
    if ts_epoch <= 0 or not math.isfinite(index_ret1):
        return None

    values = raw.get("constituent_ret1")
    if isinstance(values, Mapping):
        values = list(values.values())
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return None

    returns: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            returns.append(number)
    if len(returns) < min_constituents:
        return None

    breadth_down = sum(value < 0.0 for value in returns) / len(returns)
    breadth_mean = sum(returns) / len(returns)
    return {
        "ts_epoch": ts_epoch,
        "source_bar_end_epoch": float(raw.get("source_bar_end_epoch", ts_epoch)),
        "breadth_down_1": breadth_down,
        "breadth_mean_ret1": breadth_mean,
        "index_ret1": index_ret1,
        "index_breadth_divergence": index_ret1 - breadth_mean,
        "participation_count": len(returns),
    }


__all__ = [
    "attach_completed_constituent_breadth_snapshots",
    "produce_completed_constituent_breadth_snapshots",
]

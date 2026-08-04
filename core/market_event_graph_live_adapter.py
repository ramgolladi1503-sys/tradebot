"""Fail-closed adapter for live completed constituent-breadth events.

The adapter does not infer or tune thresholds. It accepts only completed rows that
carry an explicit event label produced by the live breadth pipeline and publishes
a canonical three-row history for StrategyContext.metadata.
"""

from __future__ import annotations

from typing import Any, Mapping

ALLOWED_EVENT_LABELS = frozenset(
    {
        "breadth_down_1:HIGH",
        "breadth_down_1:LOW",
        "index_breadth_divergence:LOW",
    }
)
SOURCE_KEYS = (
    "completed_constituent_breadth_snapshots",
    "constituent_breadth_history",
    "market_event_graph_history",
)


def build_market_event_graph_history(
    payload: Mapping[str, Any] | None,
    *,
    max_rows: int = 12,
) -> list[dict[str, Any]]:
    """Return canonical completed event rows, or an empty list on invalid input."""

    if not isinstance(payload, Mapping):
        return []

    raw: Any = None
    for key in SOURCE_KEYS:
        value = payload.get(key)
        if isinstance(value, (list, tuple)):
            raw = value
            break
    if raw is None:
        return []

    canonical: list[dict[str, Any]] = []
    for row in raw:
        item = _canonical_row(row)
        if item is not None:
            canonical.append(item)

    canonical.sort(key=lambda item: item["ts_epoch"])
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[float, str]] = set()
    for item in canonical:
        identity = (item["ts_epoch"], item["event_label"])
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(item)
    return deduped[-max(3, int(max_rows)) :]


def attach_market_event_graph_history(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Copy metadata and attach its canonical graph history when available."""

    out = dict(metadata or {})
    history = build_market_event_graph_history(out)
    if history:
        out["market_event_graph_history"] = history
        out["market_event_graph_history_status"] = "READY"
        out["market_event_graph_history_source"] = "completed_constituent_breadth_snapshots"
    else:
        out.pop("market_event_graph_history", None)
        out["market_event_graph_history_status"] = "MISSING_OR_INVALID"
    return out


def _canonical_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, Mapping):
        return None
    if row.get("completed") is False or row.get("is_completed") is False:
        return None
    label = str(row.get("event_label") or "").strip()
    if label not in ALLOWED_EVENT_LABELS:
        return None
    try:
        ts_epoch = float(row["ts_epoch"])
    except (KeyError, TypeError, ValueError):
        return None
    if ts_epoch <= 0:
        return None

    item: dict[str, Any] = {
        "event_label": label,
        "ts_epoch": ts_epoch,
        "completed": True,
    }
    for key in (
        "breadth_down_1",
        "breadth_mean_ret1",
        "index_ret1",
        "index_breadth_divergence",
        "participation_count",
        "source_bar_end_epoch",
        "session_date",
        "market_event_graph_strategy_id",
        "market_event_graph_dataset_sha256",
        "market_event_graph_frozen_spec_sha256",
        "market_event_graph_thresholds",
        "market_event_graph_triplet_id",
        "market_event_graph_signal_ts_epoch",
        "market_event_graph_entry_bar_ts_epoch",
        "allowed_for_live_execution",
        "is_order_action",
        "broker_api_called",
    ):
        if row.get(key) is not None:
            item[key] = row.get(key)
    return item


__all__ = [
    "ALLOWED_EVENT_LABELS",
    "SOURCE_KEYS",
    "attach_market_event_graph_history",
    "build_market_event_graph_history",
]

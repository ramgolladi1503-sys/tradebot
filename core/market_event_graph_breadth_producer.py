"""Causal producer for completed constituent-breadth event snapshots.

The producer is read-only and fail-closed. It consumes completed index/constituent
return snapshots plus frozen thresholds supplied by research evidence. It never
fetches data, tunes thresholds, calls a broker, or creates an order action.

The frozen research graph is positional, not an open-ended state machine:
A(t-2) -> B(t-1) -> C(t) on three consecutive completed rows.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from core.market_event_graph_contract import (
    DATASET_SHA256,
    FROZEN_DISCOVERY_SPEC_SHA256,
    FROZEN_THRESHOLDS,
    STRATEGY_ID,
    metadata_has_frozen_contract,
    thresholds_match_frozen,
)

_REQUIRED_THRESHOLD_KEYS = (
    "breadth_high",
    "breadth_low",
    "divergence_low",
)


def produce_completed_constituent_breadth_snapshots(
    metadata: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return only exact consecutive-row graph matches, or [] on invalid input."""

    if not isinstance(metadata, Mapping):
        return []
    bars = metadata.get("completed_constituent_bars")
    thresholds = metadata.get("market_event_graph_thresholds")
    if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes)):
        return []
    if not isinstance(thresholds, Mapping):
        return []
    if not bool(metadata.get("market_event_graph_allow_test_thresholds")):
        if not metadata_has_frozen_contract(metadata) or not thresholds_match_frozen(thresholds):
            return []

    parsed_thresholds = _parse_thresholds(thresholds)
    if parsed_thresholds is None:
        return []
    breadth_high, breadth_low, divergence_low, min_constituents = parsed_thresholds

    rows: list[dict[str, Any]] = []
    for raw in bars:
        row = _compute_row(raw, min_constituents=min_constituents)
        if row is None:
            return []
        rows.append(row)
    if any(rows[index]["ts_epoch"] <= rows[index - 1]["ts_epoch"] for index in range(1, len(rows))):
        return []
    rows.sort(key=lambda item: item["ts_epoch"])
    if any(rows[index]["ts_epoch"] <= rows[index - 1]["ts_epoch"] for index in range(1, len(rows))):
        return []
    if len(rows) < 3:
        return []

    events: list[dict[str, Any]] = []
    emitted_triplets = set()
    for index in range(2, len(rows) - 1):
        first, second, third = rows[index - 2 : index + 1]
        entry_bar = rows[index + 1]
        if not _valid_consecutive_window(first, second, third):
            continue
        if not (
            first["breadth_down_1"] >= breadth_high
            and second["index_breadth_divergence"] <= divergence_low
            and third["breadth_down_1"] <= breadth_low
        ):
            continue
        triplet_id = (first["ts_epoch"], second["ts_epoch"], third["ts_epoch"])
        if triplet_id in emitted_triplets:
            continue
        emitted_triplets.add(triplet_id)
        events.extend(
            (
                _event(first, "breadth_down_1:HIGH", triplet_id, entry_bar),
                {
                    **_event(second, "index_breadth_divergence:LOW", triplet_id, entry_bar),
                },
                _event(third, "breadth_down_1:LOW", triplet_id, entry_bar),
            )
        )

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


def frozen_threshold_metadata() -> dict[str, Any]:
    return {
        "market_event_graph_strategy_id": STRATEGY_ID,
        "market_event_graph_dataset_sha256": DATASET_SHA256,
        "market_event_graph_frozen_spec_sha256": FROZEN_DISCOVERY_SPEC_SHA256,
        "market_event_graph_thresholds": dict(FROZEN_THRESHOLDS),
    }


def _valid_consecutive_window(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    third: Mapping[str, Any],
) -> bool:
    if not (first["ts_epoch"] < second["ts_epoch"] < third["ts_epoch"]):
        return False
    sessions = {first.get("session_date"), second.get("session_date"), third.get("session_date")}
    if len(sessions) != 1 or None in sessions:
        return False
    return (
        first["source_bar_end_epoch"] <= first["ts_epoch"]
        and second["source_bar_end_epoch"] <= second["ts_epoch"]
        and third["source_bar_end_epoch"] <= third["ts_epoch"]
    )


def _event(
    row: Mapping[str, Any],
    label: str,
    triplet_id: tuple[float, float, float],
    entry_bar: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **row,
        "event_label": label,
        "completed": True,
        "market_event_graph_strategy_id": STRATEGY_ID,
        "market_event_graph_dataset_sha256": DATASET_SHA256,
        "market_event_graph_frozen_spec_sha256": FROZEN_DISCOVERY_SPEC_SHA256,
        "market_event_graph_thresholds": dict(FROZEN_THRESHOLDS),
        "market_event_graph_triplet_id": "|".join(f"{value:.6f}" for value in triplet_id),
        "market_event_graph_signal_ts_epoch": triplet_id[-1],
        "market_event_graph_entry_bar_ts_epoch": entry_bar["ts_epoch"],
        "allowed_for_live_execution": False,
        "is_order_action": False,
        "broker_api_called": False,
    }


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
    try:
        source_bar_end_epoch = float(raw.get("source_bar_end_epoch", ts_epoch))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(source_bar_end_epoch) or source_bar_end_epoch > ts_epoch:
        return None
    session_date = str(raw.get("session_date") or "").strip()
    if not session_date:
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
        "source_bar_end_epoch": source_bar_end_epoch,
        "session_date": session_date,
        "breadth_down_1": breadth_down,
        "breadth_mean_ret1": breadth_mean,
        "index_ret1": index_ret1,
        "index_breadth_divergence": index_ret1 - breadth_mean,
        "participation_count": len(returns),
    }


__all__ = [
    "attach_completed_constituent_breadth_snapshots",
    "frozen_threshold_metadata",
    "produce_completed_constituent_breadth_snapshots",
]

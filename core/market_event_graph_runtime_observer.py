"""Read-only runtime availability observer for the market-event graph strategy.

This module answers the operational question that precedes profitability: whether
completed constituent-breadth input is arriving, whether it is causal/aligned,
and whether the producer and adapter accept it.  It does not subscribe to feeds,
mutate strategy state, call a broker, or authorize an order.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from core.market_event_graph_breadth_producer import (
    attach_completed_constituent_breadth_snapshots,
)
from core.market_event_graph_contract import (
    FROZEN_GRAPH,
    FROZEN_THRESHOLDS,
    metadata_has_frozen_contract,
    thresholds_match_frozen,
)
from core.market_event_graph_live_adapter import attach_market_event_graph_history

OBSERVATION_SCHEMA_VERSION = 1
MAX_SOURCE_AGE_SEC = 420.0


def observe_market_event_graph_runtime(
    metadata: Mapping[str, Any] | None,
    *,
    context_ts: float | None = None,
) -> dict[str, Any]:
    """Return causal availability, rejection, partial-sequence, and adapter evidence."""

    base = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "strategy_id": "market_event_graph_reversal_v1",
        "status": "MISSING_METADATA",
        "reason": "metadata_not_mapping",
        "source_interval_count": 0,
        "accepted_interval_count": 0,
        "rejected_interval_count": 0,
        "rejection_counts": {},
        "label_counts": {},
        "partial_sequence_length": 0,
        "partial_sequence_labels": [],
        "graph_trigger_count": 0,
        "producer_status": "NOT_EVALUATED",
        "adapter_status": "NOT_EVALUATED",
        "adapter_row_count": 0,
        "latest_source_bar_end_epoch": None,
        "latest_source_age_sec": None,
        "source_fresh": False,
        "session_dates": [],
        "allowed_for_live_execution": False,
        "is_order_action": False,
        "broker_api_called": False,
    }
    if not isinstance(metadata, Mapping):
        return base

    out = dict(base)
    raw_bars = metadata.get("completed_constituent_bars")
    if not isinstance(raw_bars, Sequence) or isinstance(raw_bars, (str, bytes)):
        out.update(status="MISSING_SOURCE_BARS", reason="completed_constituent_bars_missing")
        return out

    out["source_interval_count"] = len(raw_bars)
    thresholds = metadata.get("market_event_graph_thresholds")
    if not isinstance(thresholds, Mapping):
        out.update(status="CONTRACT_INVALID", reason="frozen_thresholds_missing")
        return out
    if not metadata_has_frozen_contract(metadata) or not thresholds_match_frozen(thresholds):
        out.update(status="CONTRACT_INVALID", reason="frozen_contract_mismatch")
        return out

    rejection_counts: Counter[str] = Counter()
    accepted: list[dict[str, Any]] = []
    prior_ts: float | None = None
    prior_source_end: float | None = None
    prior_session: str | None = None

    for raw in raw_bars:
        parsed, reason = _parse_completed_interval(raw)
        if parsed is None:
            rejection_counts[reason] += 1
            continue
        if prior_ts is not None and parsed["ts_epoch"] <= prior_ts:
            rejection_counts["timestamp_not_strictly_increasing"] += 1
            continue
        if prior_source_end is not None and parsed["source_bar_end_epoch"] <= prior_source_end:
            rejection_counts["source_bar_end_not_strictly_increasing"] += 1
            continue
        if prior_session is not None and parsed["session_date"] != prior_session:
            rejection_counts["session_changed_within_payload"] += 1
            continue
        accepted.append(parsed)
        prior_ts = parsed["ts_epoch"]
        prior_source_end = parsed["source_bar_end_epoch"]
        prior_session = parsed["session_date"]

    out["accepted_interval_count"] = len(accepted)
    out["rejected_interval_count"] = len(raw_bars) - len(accepted)
    out["rejection_counts"] = dict(sorted(rejection_counts.items()))
    out["session_dates"] = sorted({row["session_date"] for row in accepted})

    if not accepted:
        out.update(status="NO_VALID_COMPLETED_INTERVALS", reason="all_source_intervals_rejected")
        return out

    latest_source_end = float(accepted[-1]["source_bar_end_epoch"])
    out["latest_source_bar_end_epoch"] = latest_source_end
    if context_ts is not None:
        try:
            age = float(context_ts) - latest_source_end
        except (TypeError, ValueError):
            age = math.inf
        if math.isfinite(age):
            out["latest_source_age_sec"] = age
            out["source_fresh"] = 0.0 <= age <= MAX_SOURCE_AGE_SEC

    labelled_rows = [_labels_for_row(row) for row in accepted]
    label_counts: Counter[str] = Counter(label for labels in labelled_rows for label in labels)
    out["label_counts"] = dict(sorted(label_counts.items()))
    partial = _latest_partial_sequence(labelled_rows)
    out["partial_sequence_length"] = len(partial)
    out["partial_sequence_labels"] = list(partial)

    producer_payload = attach_completed_constituent_breadth_snapshots(metadata)
    out["producer_status"] = str(
        producer_payload.get("constituent_breadth_producer_status") or "MISSING_OR_INVALID"
    )
    adapted = attach_market_event_graph_history(producer_payload)
    out["adapter_status"] = str(adapted.get("market_event_graph_history_status") or "MISSING_OR_INVALID")
    history = adapted.get("market_event_graph_history")
    if isinstance(history, list):
        out["adapter_row_count"] = len(history)
        out["graph_trigger_count"] = sum(
            1
            for index in range(2, len(history))
            if tuple(str(history[pos].get("event_label") or "") for pos in range(index - 2, index + 1))
            == FROZEN_GRAPH
        )

    if out["adapter_status"] == "READY" and out["graph_trigger_count"] > 0:
        out.update(status="GRAPH_READY", reason="producer_and_adapter_accepted_frozen_graph")
    elif partial:
        out.update(status="PARTIAL_SEQUENCE", reason="causal_partial_graph_observed")
    elif not out["source_fresh"] and context_ts is not None:
        out.update(status="SOURCE_STALE", reason="latest_completed_interval_outside_freshness_window")
    else:
        out.update(status="RUNTIME_AVAILABLE", reason="valid_completed_intervals_no_graph")
    return out


def _parse_completed_interval(raw: Any) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(raw, Mapping):
        return None, "row_not_mapping"
    if raw.get("completed") is False or raw.get("is_completed") is False:
        return None, "row_incomplete"
    try:
        ts_epoch = float(raw["ts_epoch"])
        source_bar_end_epoch = float(raw.get("source_bar_end_epoch", ts_epoch))
        index_ret1 = float(raw["index_ret1"])
    except (KeyError, TypeError, ValueError):
        return None, "row_numeric_fields_invalid"
    if not all(math.isfinite(value) for value in (ts_epoch, source_bar_end_epoch, index_ret1)):
        return None, "row_numeric_fields_non_finite"
    if ts_epoch <= 0.0 or source_bar_end_epoch <= 0.0 or source_bar_end_epoch > ts_epoch:
        return None, "row_timestamp_contract_invalid"
    session_date = str(raw.get("session_date") or "").strip()
    if not session_date:
        return None, "row_session_missing"

    values = raw.get("constituent_ret1")
    if isinstance(values, Mapping):
        values = list(values.values())
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return None, "constituent_returns_missing"
    returns: list[float] = []
    for value in values:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed):
            returns.append(parsed)
    if len(returns) < int(FROZEN_THRESHOLDS["min_constituents"]):
        return None, "constituent_coverage_below_minimum"

    breadth_down = sum(value < 0.0 for value in returns) / len(returns)
    breadth_mean = sum(returns) / len(returns)
    return (
        {
            "ts_epoch": ts_epoch,
            "source_bar_end_epoch": source_bar_end_epoch,
            "session_date": session_date,
            "index_ret1": index_ret1,
            "breadth_down_1": breadth_down,
            "breadth_mean_ret1": breadth_mean,
            "index_breadth_divergence": index_ret1 - breadth_mean,
            "participation_count": len(returns),
        },
        "accepted",
    )


def _labels_for_row(row: Mapping[str, Any]) -> tuple[str, ...]:
    labels: list[str] = []
    if float(row["breadth_down_1"]) >= float(FROZEN_THRESHOLDS["breadth_high"]):
        labels.append(FROZEN_GRAPH[0])
    if float(row["index_breadth_divergence"]) <= float(FROZEN_THRESHOLDS["divergence_low"]):
        labels.append(FROZEN_GRAPH[1])
    if float(row["breadth_down_1"]) <= float(FROZEN_THRESHOLDS["breadth_low"]):
        labels.append(FROZEN_GRAPH[2])
    return tuple(labels)


def _latest_partial_sequence(labelled_rows: Sequence[tuple[str, ...]]) -> tuple[str, ...]:
    if not labelled_rows:
        return ()
    if len(labelled_rows) >= 3 and all(
        expected in labelled_rows[-3 + offset] for offset, expected in enumerate(FROZEN_GRAPH)
    ):
        return FROZEN_GRAPH
    if len(labelled_rows) >= 2 and FROZEN_GRAPH[0] in labelled_rows[-2] and FROZEN_GRAPH[1] in labelled_rows[-1]:
        return FROZEN_GRAPH[:2]
    if FROZEN_GRAPH[0] in labelled_rows[-1]:
        return FROZEN_GRAPH[:1]
    return ()


__all__ = [
    "MAX_SOURCE_AGE_SEC",
    "OBSERVATION_SCHEMA_VERSION",
    "observe_market_event_graph_runtime",
]

"""Read-only PR #749 constituent-source refresh coordinator.

This module owns activation cadence only. It does not create market-data
connections, place orders, rank candidates, or change graph thresholds.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from core.market_event_graph_constituent_source import (
    DEFAULT_COMPLETION_GRACE_SEC,
    DEFAULT_STATE_PATH,
    attach_market_event_graph_constituent_source,
    persist_market_event_graph_constituent_state,
)
from core.time_utils import IST_TZ

REFRESH_SCHEMA_VERSION = 1
_REFRESH_LOCK = threading.RLock()
_LAST_REFRESH_BY_KEY: dict[tuple[str, str, int | None], int] = {}
_SUBSCRIPTION_ENSURED_BY_KEY: set[tuple[str, str, int | None]] = set()
_COUNTERS = {
    "refresh_invocation_count": 0,
    "subscription_ensure_count": 0,
    "subscription_mutation_count": 0,
    "state_create_count": 0,
    "state_persist_count": 0,
}


def refresh_market_event_graph_constituent_source(
    *,
    symbol: str,
    as_of_epoch: float,
    metadata: Mapping[str, Any] | None = None,
    enabled: bool | None = None,
    **attach_kwargs: Any,
) -> dict[str, Any]:
    """Invoke and persist the PR #749 source on a completed-boundary cadence."""

    started_epoch = time.time()
    base_metadata = dict(metadata or {})
    owner = str(base_metadata.get("owner") or base_metadata.get("identity") or symbol or "").strip().upper()
    state_path = _state_path(base_metadata, attach_kwargs.get("state_path"))
    attach_kwargs.pop("state_path", None)
    state_existed_before = state_path.is_file()
    try:
        parsed_epoch = float(as_of_epoch)
    except (TypeError, ValueError):
        parsed_epoch = 0.0
    if not math.isfinite(parsed_epoch) or parsed_epoch <= 0.0:
        result = _result(
            invoked=True,
            status="INVALID_CONTEXT_TIME",
            reason="as_of_epoch_missing_or_invalid",
            symbol=symbol,
            owner=owner,
            as_of_epoch=as_of_epoch,
            session_date=None,
            feed_session_id=base_metadata.get("feed_session_id"),
            reconnect_generation=_optional_int(base_metadata.get("reconnect_generation")),
            mutation_generation=base_metadata.get("mutation_generation"),
            latest_completed_boundary_epoch=None,
            state_path=state_path,
            state_existed_before=state_existed_before,
            state_exists_after=state_path.is_file(),
            state_persisted=False,
            producer_metadata=base_metadata,
        )
        result["duration_ms"] = round((time.time() - started_epoch) * 1000.0, 3)
        _observe_refresh(result, base_metadata)
        return result
    try:
        session_date = datetime.fromtimestamp(parsed_epoch, tz=IST_TZ).date().isoformat()
        reconnect_generation = _optional_int(base_metadata.get("reconnect_generation"))
        feed_session_id = base_metadata.get("feed_session_id")
        boundary = _completed_boundary(parsed_epoch)
        key = (str(symbol or "").strip().upper(), session_date, reconnect_generation)
        with _REFRESH_LOCK:
            prior_boundary = _LAST_REFRESH_BY_KEY.get(key)
            subscription_needed = key not in _SUBSCRIPTION_ENSURED_BY_KEY
            if prior_boundary is not None and boundary <= prior_boundary:
                result = _result(
                    invoked=False,
                    status="SKIPPED_SAME_BOUNDARY",
                    reason="completed_boundary_already_processed",
                    symbol=symbol,
                    owner=owner,
                    as_of_epoch=parsed_epoch,
                    session_date=session_date,
                    feed_session_id=feed_session_id,
                    reconnect_generation=reconnect_generation,
                    mutation_generation=base_metadata.get("mutation_generation"),
                    latest_completed_boundary_epoch=boundary,
                    state_path=state_path,
                    state_existed_before=state_existed_before,
                    state_exists_after=state_path.is_file(),
                    state_persisted=False,
                    producer_metadata=base_metadata,
                )
                _observe_refresh(result, base_metadata)
                return result
            _COUNTERS["refresh_invocation_count"] += 1
            subscription_fn = attach_kwargs.pop("subscription_fn", None)
            if not subscription_needed:
                subscription_fn = lambda tokens: True
            else:
                _COUNTERS["subscription_ensure_count"] += 1
            source_metadata = attach_market_event_graph_constituent_source(
                base_metadata,
                symbol=symbol,
                as_of_epoch=parsed_epoch,
                enabled=enabled,
                state_path=state_path,
                subscription_fn=subscription_fn,
                **attach_kwargs,
            )
            source_metadata.setdefault(
                "market_event_graph_constituent_source_evidence",
                {
                    "subscription_ok": False,
                    "completed_bar_count": len(source_metadata.get("completed_constituent_bars") or []),
                    "last_build_failures": [],
                    "target_boundary_count": 0,
                    "target_boundaries": [],
                    "reader_visible_row_count": 0,
                    "read_only": True,
                    "is_order_action": False,
                    "broker_api_called": False,
                    "allowed_for_live_execution": False,
                },
            )
            state_persisted = persist_market_event_graph_constituent_state(source_metadata)
            if state_persisted:
                _COUNTERS["state_persist_count"] += 1
            if not state_existed_before and state_path.is_file():
                _COUNTERS["state_create_count"] += 1
            if subscription_needed:
                _SUBSCRIPTION_ENSURED_BY_KEY.add(key)
                if _subscription_ok(source_metadata):
                    _COUNTERS["subscription_mutation_count"] += 1
            _LAST_REFRESH_BY_KEY[key] = boundary
        result = _result(
            invoked=True,
            status=str(source_metadata.get("market_event_graph_constituent_source_status") or "UNKNOWN"),
            reason=str(source_metadata.get("market_event_graph_constituent_source_reason") or "unknown"),
            symbol=symbol,
            owner=owner,
            as_of_epoch=parsed_epoch,
            session_date=session_date,
            feed_session_id=feed_session_id,
            reconnect_generation=reconnect_generation,
            mutation_generation=base_metadata.get("mutation_generation"),
            latest_completed_boundary_epoch=boundary,
            state_path=state_path,
            state_existed_before=state_existed_before,
            state_exists_after=state_path.is_file(),
            state_persisted=state_persisted,
            producer_metadata=source_metadata,
        )
        result["duration_ms"] = round((time.time() - started_epoch) * 1000.0, 3)
        _observe_refresh(result, source_metadata)
        return result
    except Exception as exc:
        result = _result(
            invoked=True,
            status="PR749_SOURCE_REFRESH_FAILED",
            reason=f"{type(exc).__name__}:{exc}",
            symbol=symbol,
            owner=owner,
            as_of_epoch=as_of_epoch,
            session_date=None,
            feed_session_id=base_metadata.get("feed_session_id"),
            reconnect_generation=_optional_int(base_metadata.get("reconnect_generation")),
            mutation_generation=base_metadata.get("mutation_generation"),
            latest_completed_boundary_epoch=None,
            state_path=state_path,
            state_existed_before=state_existed_before,
            state_exists_after=state_path.is_file(),
            state_persisted=False,
            producer_metadata=base_metadata,
        )
        result["exception_type"] = type(exc).__name__
        result["stage"] = "refresh_market_event_graph_constituent_source"
        result["duration_ms"] = round((time.time() - started_epoch) * 1000.0, 3)
        _observe_refresh(result, base_metadata)
        return result


def reset_market_event_graph_constituent_refresh_state() -> None:
    """Reset process-local cadence state for deterministic tests."""

    with _REFRESH_LOCK:
        _LAST_REFRESH_BY_KEY.clear()
        _SUBSCRIPTION_ENSURED_BY_KEY.clear()
        for key in _COUNTERS:
            _COUNTERS[key] = 0


def persist_market_event_graph_constituent_refresh_state(metadata: Mapping[str, Any] | None) -> bool:
    """Persist PR #749 runtime state through the shared refresh owner."""

    persisted = persist_market_event_graph_constituent_state(metadata)
    if persisted:
        with _REFRESH_LOCK:
            _COUNTERS["state_persist_count"] += 1
    return bool(persisted)


def _result(
    *,
    invoked: bool,
    status: str,
    reason: str,
    symbol: str,
    owner: str,
    as_of_epoch: Any,
    session_date: str | None,
    feed_session_id: Any,
    reconnect_generation: int | None,
    mutation_generation: Any,
    latest_completed_boundary_epoch: int | None,
    state_path: Path,
    state_existed_before: bool,
    state_exists_after: bool,
    state_persisted: bool,
    producer_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = producer_metadata.get("market_event_graph_constituent_source_evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    completed_bars = producer_metadata.get("completed_constituent_bars")
    completed_bar_count = len(completed_bars) if isinstance(completed_bars, list) else 0
    target_boundary_count = int(evidence.get("target_boundary_count") or 0)
    out = {
        "schema_version": REFRESH_SCHEMA_VERSION,
        "invoked": bool(invoked),
        "status": status,
        "reason": reason,
        "producer_status": producer_metadata.get("market_event_graph_constituent_source_status", status),
        "producer_reason": producer_metadata.get("market_event_graph_constituent_source_reason", reason),
        "symbol": str(symbol or "").strip().upper(),
        "owner": owner,
        "identity": owner,
        "as_of_epoch": as_of_epoch,
        "session_date": session_date,
        "feed_session_id": feed_session_id,
        "reconnect_generation": reconnect_generation,
        "mutation_generation": mutation_generation,
        "latest_completed_boundary_epoch": latest_completed_boundary_epoch,
        "target_boundary_count": target_boundary_count,
        "target_boundaries": list(evidence.get("target_boundaries") or []),
        "reader_visible_row_count": int(evidence.get("reader_visible_row_count") or 0),
        "completed_bar_count": completed_bar_count,
        "last_build_failures": list(evidence.get("last_build_failures") or []),
        "state_path": str(state_path),
        "state_existed_before": bool(state_existed_before),
        "state_exists_after": bool(state_exists_after),
        "state_created": bool((not state_existed_before) and state_exists_after),
        "state_persisted": bool(state_persisted),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "producer_metadata": dict(producer_metadata),
    }
    out.update(_COUNTERS)
    return out


def _observe_refresh(result: Mapping[str, Any], metadata: Mapping[str, Any]) -> None:
    observed = dict(metadata)
    refresh_row = dict(result)
    refresh_row.pop("producer_metadata", None)
    observed["market_event_graph_constituent_refresh"] = refresh_row
    observed["market_event_graph_constituent_source_status"] = result.get("producer_status")
    observed["market_event_graph_constituent_source_reason"] = result.get("producer_reason")
    observed.setdefault(
        "market_event_graph_constituent_source_evidence",
        {
            "subscription_ok": False,
            "completed_bar_count": result.get("completed_bar_count", 0),
            "last_build_failures": result.get("last_build_failures", []),
            "target_boundary_count": result.get("target_boundary_count", 0),
            "target_boundaries": result.get("target_boundaries", []),
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        },
    )
    try:
        from core.unified_live_validation_pr748_756.runtime_observer import safe_call

        safe_call(
            "observe_constituent_source",
            observed,
            source="core.market_event_graph_constituent_refresh.refresh_market_event_graph_constituent_source",
        )
        safe_call(
            "observe_subscription",
            dict(result),
            source="core.market_event_graph_constituent_refresh.refresh_market_event_graph_constituent_source",
        )
    except Exception:
        pass


def _state_path(metadata: Mapping[str, Any], explicit: Any) -> Path:
    import os

    raw = (
        explicit
        or metadata.get("market_event_graph_constituent_source_state_path")
        or os.getenv("MARKET_EVENT_GRAPH_LIVE_STATE_PATH")
        or DEFAULT_STATE_PATH
    )
    return Path(raw).expanduser().resolve()


def _completed_boundary(as_of_epoch: float) -> int:
    return int(math.floor((float(as_of_epoch) - DEFAULT_COMPLETION_GRACE_SEC) / 60.0) * 60.0)


def _optional_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _subscription_ok(metadata: Mapping[str, Any]) -> bool:
    evidence = metadata.get("market_event_graph_constituent_source_evidence")
    if isinstance(evidence, Mapping):
        return bool(evidence.get("subscription_ok"))
    return False


__all__ = [
    "persist_market_event_graph_constituent_refresh_state",
    "refresh_market_event_graph_constituent_source",
    "reset_market_event_graph_constituent_refresh_state",
]

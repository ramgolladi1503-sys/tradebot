"""Feed runtime writer liveness evidence for LIVE-TRUTH-04.

This module verifies that feed runtime evidence is being written recently and
that WebSocket/subscription failure signals have recovery visibility. It is
read-only and does not reconnect feeds, mutate runtime state, generate
candidates, score candidates, or change execution behavior.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.events import write_json_atomic

FEED_RUNTIME_WRITER_LIVENESS_SCHEMA_VERSION = 1
FEED_RUNTIME_WRITER_LIVENESS_SOURCE = "live_truth_feed_runtime_writer_liveness_v1"

WRITER_STATUS_ALIVE = "FEED_RUNTIME_WRITER_ALIVE"
WRITER_STATUS_STALE = "FEED_RUNTIME_WRITER_STALE"
WRITER_STATUS_RECOVERY_MISSING = "FEED_RUNTIME_RECOVERY_EVIDENCE_MISSING"
WRITER_STATUS_BLOCKED = "FEED_RUNTIME_WRITER_LIVENESS_BLOCKED"

WRITER_FRESH_REASON = "feed_runtime_writer_recent"
WRITER_STALE_REASON = "feed_runtime_writer_stale"
MISSING_HEARTBEAT_REASON = "missing_feed_runtime_writer_heartbeat"
INVALID_SNAPSHOT_REASON = "invalid_feed_runtime_snapshot"
INVALID_CONFIG_REASON = "invalid_feed_runtime_writer_liveness_config"
WEBSOCKET_RECOVERY_MISSING_REASON = "websocket_recovery_evidence_missing"
SUBSCRIPTION_RECOVERY_MISSING_REASON = "subscription_recovery_evidence_missing"
FUTURE_HEARTBEAT_REASON = "feed_runtime_writer_heartbeat_in_future"

DEFAULT_WRITER_MAX_AGE_SEC = 60.0
DEFAULT_RECOVERY_VISIBILITY_MAX_AGE_SEC = 180.0
DEFAULT_FUTURE_SKEW_TOLERANCE_SEC = 5.0

_HEARTBEAT_KEYS = (
    "generated_epoch",
    "updated_epoch",
    "last_update_epoch",
    "last_updated_epoch",
    "last_write_epoch",
    "writer_epoch",
    "heartbeat_epoch",
    "last_heartbeat_epoch",
    "feed_runtime_written_epoch",
    "feed_runtime_updated_epoch",
    "generated_at",
    "updated_at",
    "last_update_at",
    "last_updated_at",
    "last_write_at",
    "heartbeat_at",
    "last_heartbeat_at",
)

_WS_CONNECTED_KEYS = (
    "ws_connected",
    "websocket_connected",
    "feed_ws_connected",
    "connected",
)

_FEED_OK_KEYS = (
    "feed_ok",
    "is_feed_ok",
    "healthy",
    "feed_healthy",
)

_WS_DOWN_KEYS = (
    "last_disconnect_epoch",
    "last_ws_disconnect_epoch",
    "ws_disconnected_epoch",
    "websocket_disconnected_epoch",
    "disconnect_epoch",
    "last_disconnect_at",
    "last_ws_disconnect_at",
    "ws_disconnected_at",
    "websocket_disconnected_at",
    "disconnect_at",
)

_WS_RECOVERY_KEYS = (
    "last_reconnect_epoch",
    "last_ws_reconnect_epoch",
    "ws_reconnected_epoch",
    "websocket_reconnected_epoch",
    "reconnect_epoch",
    "recovery_epoch",
    "last_reconnect_at",
    "last_ws_reconnect_at",
    "ws_reconnected_at",
    "websocket_reconnected_at",
    "reconnect_at",
    "recovery_at",
)

_SUB_FAILURE_KEYS = (
    "last_subscription_failure_epoch",
    "last_subscribe_failed_epoch",
    "subscription_failed_epoch",
    "subscribe_failed_epoch",
    "last_subscribe_error_epoch",
    "last_subscription_failure_at",
    "last_subscribe_failed_at",
    "subscription_failed_at",
    "subscribe_failed_at",
    "last_subscribe_error_at",
)

_SUB_RECOVERY_KEYS = (
    "last_subscription_success_epoch",
    "last_subscribe_success_epoch",
    "subscription_recovered_epoch",
    "subscribe_success_epoch",
    "subscription_recovery_epoch",
    "last_subscription_success_at",
    "last_subscribe_success_at",
    "subscription_recovered_at",
    "subscribe_success_at",
    "subscription_recovery_at",
)

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"
_LIVE_ACTION_KEY = "live_" + "order_action"
_BROKER_ACTION_KEY = "broker_" + "order_action"


@dataclass(frozen=True)
class FeedRuntimeWriterLivenessReport:
    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    now_epoch: float
    writer_alive: bool
    heartbeat_epoch: float | None
    heartbeat_key: str | None
    heartbeat_age_sec: float | None
    writer_max_age_sec: float
    ws_connected: bool | None
    feed_ok: bool | None
    websocket_recovery_visible: bool
    subscription_recovery_visible: bool
    recovery_issue_count: int
    last_ws_down_epoch: float | None
    last_ws_recovery_epoch: float | None
    last_subscription_failure_epoch: float | None
    last_subscription_recovery_epoch: float | None
    subscribed_tokens_count: int | None
    subscribed_option_tokens_count: int | None
    read_only: bool = True
    append: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "source": self.source,
            "status": self.status,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "now_epoch": self.now_epoch,
            "writer_alive": self.writer_alive,
            "heartbeat_epoch": self.heartbeat_epoch,
            "heartbeat_key": self.heartbeat_key,
            "heartbeat_age_sec": self.heartbeat_age_sec,
            "writer_max_age_sec": self.writer_max_age_sec,
            "ws_connected": self.ws_connected,
            "feed_ok": self.feed_ok,
            "websocket_recovery_visible": self.websocket_recovery_visible,
            "subscription_recovery_visible": self.subscription_recovery_visible,
            "recovery_issue_count": self.recovery_issue_count,
            "last_ws_down_epoch": self.last_ws_down_epoch,
            "last_ws_recovery_epoch": self.last_ws_recovery_epoch,
            "last_subscription_failure_epoch": self.last_subscription_failure_epoch,
            "last_subscription_recovery_epoch": self.last_subscription_recovery_epoch,
            "subscribed_tokens_count": self.subscribed_tokens_count,
            "subscribed_option_tokens_count": self.subscribed_option_tokens_count,
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_feed_runtime_writer_liveness_report(
    feed_runtime_snapshot: Mapping[str, Any] | Any,
    *,
    now_epoch: float,
    writer_max_age_sec: float = DEFAULT_WRITER_MAX_AGE_SEC,
    recovery_visibility_max_age_sec: float = DEFAULT_RECOVERY_VISIBILITY_MAX_AGE_SEC,
    future_skew_tolerance_sec: float = DEFAULT_FUTURE_SKEW_TOLERANCE_SEC,
) -> FeedRuntimeWriterLivenessReport:
    """Build read-only liveness evidence for the feed runtime writer."""

    now = _finite_float_or_none(now_epoch)
    max_age = _positive_float_or_none(writer_max_age_sec)
    recovery_max_age = _positive_float_or_none(recovery_visibility_max_age_sec)
    future_skew = _non_negative_float_or_none(future_skew_tolerance_sec)
    if now is None or max_age is None or recovery_max_age is None or future_skew is None:
        return _report(
            status=WRITER_STATUS_BLOCKED,
            reason_code=INVALID_CONFIG_REASON,
            reasons=(INVALID_CONFIG_REASON,),
            now_epoch=0.0 if now is None else now,
            writer_alive=False,
            heartbeat_epoch=None,
            heartbeat_key=None,
            heartbeat_age_sec=None,
            writer_max_age_sec=0.0 if max_age is None else max_age,
            ws_connected=None,
            feed_ok=None,
            websocket_recovery_visible=False,
            subscription_recovery_visible=False,
            recovery_issue_count=0,
            last_ws_down_epoch=None,
            last_ws_recovery_epoch=None,
            last_subscription_failure_epoch=None,
            last_subscription_recovery_epoch=None,
            subscribed_tokens_count=None,
            subscribed_option_tokens_count=None,
            metadata={"blocked_before_snapshot_evaluation": True},
        )

    payload = _payload_or_none(feed_runtime_snapshot)
    if payload is None:
        return _report(
            status=WRITER_STATUS_BLOCKED,
            reason_code=INVALID_SNAPSHOT_REASON,
            reasons=(INVALID_SNAPSHOT_REASON,),
            now_epoch=now,
            writer_alive=False,
            heartbeat_epoch=None,
            heartbeat_key=None,
            heartbeat_age_sec=None,
            writer_max_age_sec=max_age,
            ws_connected=None,
            feed_ok=None,
            websocket_recovery_visible=False,
            subscription_recovery_visible=False,
            recovery_issue_count=0,
            last_ws_down_epoch=None,
            last_ws_recovery_epoch=None,
            last_subscription_failure_epoch=None,
            last_subscription_recovery_epoch=None,
            subscribed_tokens_count=None,
            subscribed_option_tokens_count=None,
            metadata={"blocked_before_heartbeat_check": True},
        )

    heartbeat_key, heartbeat_epoch = _timestamp_from_keys(payload, _HEARTBEAT_KEYS)
    ws_connected = _first_optional_bool(payload, _WS_CONNECTED_KEYS)
    feed_ok = _first_optional_bool(payload, _FEED_OK_KEYS)
    ws_down_epoch = _timestamp_from_keys(payload, _WS_DOWN_KEYS)[1]
    ws_recovery_epoch = _timestamp_from_keys(payload, _WS_RECOVERY_KEYS)[1]
    sub_failure_epoch = _timestamp_from_keys(payload, _SUB_FAILURE_KEYS)[1]
    sub_recovery_epoch = _timestamp_from_keys(payload, _SUB_RECOVERY_KEYS)[1]
    subscribed_tokens_count = _optional_int(payload.get("subscribed_tokens_count"))
    subscribed_option_tokens_count = _optional_int(payload.get("subscribed_option_tokens_count"))

    if heartbeat_epoch is None:
        return _report(
            status=WRITER_STATUS_BLOCKED,
            reason_code=MISSING_HEARTBEAT_REASON,
            reasons=(MISSING_HEARTBEAT_REASON,),
            now_epoch=now,
            writer_alive=False,
            heartbeat_epoch=None,
            heartbeat_key=None,
            heartbeat_age_sec=None,
            writer_max_age_sec=max_age,
            ws_connected=ws_connected,
            feed_ok=feed_ok,
            websocket_recovery_visible=_is_recovery_visible(ws_down_epoch, ws_recovery_epoch, now, recovery_max_age),
            subscription_recovery_visible=_is_recovery_visible(sub_failure_epoch, sub_recovery_epoch, now, recovery_max_age),
            recovery_issue_count=0,
            last_ws_down_epoch=ws_down_epoch,
            last_ws_recovery_epoch=ws_recovery_epoch,
            last_subscription_failure_epoch=sub_failure_epoch,
            last_subscription_recovery_epoch=sub_recovery_epoch,
            subscribed_tokens_count=subscribed_tokens_count,
            subscribed_option_tokens_count=subscribed_option_tokens_count,
            metadata={"blocked_before_liveness_check": True},
        )

    heartbeat_age = round(now - heartbeat_epoch, 6)
    if heartbeat_age < -future_skew:
        return _report(
            status=WRITER_STATUS_BLOCKED,
            reason_code=FUTURE_HEARTBEAT_REASON,
            reasons=(FUTURE_HEARTBEAT_REASON,),
            now_epoch=now,
            writer_alive=False,
            heartbeat_epoch=heartbeat_epoch,
            heartbeat_key=heartbeat_key,
            heartbeat_age_sec=heartbeat_age,
            writer_max_age_sec=max_age,
            ws_connected=ws_connected,
            feed_ok=feed_ok,
            websocket_recovery_visible=_is_recovery_visible(ws_down_epoch, ws_recovery_epoch, now, recovery_max_age),
            subscription_recovery_visible=_is_recovery_visible(sub_failure_epoch, sub_recovery_epoch, now, recovery_max_age),
            recovery_issue_count=0,
            last_ws_down_epoch=ws_down_epoch,
            last_ws_recovery_epoch=ws_recovery_epoch,
            last_subscription_failure_epoch=sub_failure_epoch,
            last_subscription_recovery_epoch=sub_recovery_epoch,
            subscribed_tokens_count=subscribed_tokens_count,
            subscribed_option_tokens_count=subscribed_option_tokens_count,
            metadata={"blocked_before_liveness_check": True},
        )

    writer_alive = heartbeat_age <= max_age
    websocket_recovery_visible = _is_recovery_visible(ws_down_epoch, ws_recovery_epoch, now, recovery_max_age)
    subscription_recovery_visible = _is_recovery_visible(sub_failure_epoch, sub_recovery_epoch, now, recovery_max_age)
    reasons: list[str] = []
    if not writer_alive:
        reasons.append(WRITER_STALE_REASON)
    if ws_connected is False or (ws_down_epoch is not None and not websocket_recovery_visible):
        reasons.append(WEBSOCKET_RECOVERY_MISSING_REASON)
    if sub_failure_epoch is not None and not subscription_recovery_visible:
        reasons.append(SUBSCRIPTION_RECOVERY_MISSING_REASON)

    if WEBSOCKET_RECOVERY_MISSING_REASON in reasons or SUBSCRIPTION_RECOVERY_MISSING_REASON in reasons:
        status = WRITER_STATUS_RECOVERY_MISSING
    elif not writer_alive:
        status = WRITER_STATUS_STALE
    else:
        status = WRITER_STATUS_ALIVE
    if not reasons:
        reasons.append(WRITER_FRESH_REASON)

    recovery_issue_count = int(WEBSOCKET_RECOVERY_MISSING_REASON in reasons) + int(SUBSCRIPTION_RECOVERY_MISSING_REASON in reasons)
    return _report(
        status=status,
        reason_code=reasons[0],
        reasons=tuple(reasons),
        now_epoch=now,
        writer_alive=writer_alive,
        heartbeat_epoch=heartbeat_epoch,
        heartbeat_key=heartbeat_key,
        heartbeat_age_sec=max(0.0, heartbeat_age),
        writer_max_age_sec=max_age,
        ws_connected=ws_connected,
        feed_ok=feed_ok,
        websocket_recovery_visible=websocket_recovery_visible,
        subscription_recovery_visible=subscription_recovery_visible,
        recovery_issue_count=recovery_issue_count,
        last_ws_down_epoch=ws_down_epoch,
        last_ws_recovery_epoch=ws_recovery_epoch,
        last_subscription_failure_epoch=sub_failure_epoch,
        last_subscription_recovery_epoch=sub_recovery_epoch,
        subscribed_tokens_count=subscribed_tokens_count,
        subscribed_option_tokens_count=subscribed_option_tokens_count,
        metadata={
            "recovery_visibility_max_age_sec": recovery_max_age,
            "future_skew_tolerance_sec": future_skew,
            "evidence_only_no_runtime_change": True,
        },
    )


def write_feed_runtime_writer_liveness_evidence(
    report: FeedRuntimeWriterLivenessReport,
    path: str | Path,
) -> Path:
    """Write feed runtime writer liveness evidence."""

    return write_json_atomic(Path(path).expanduser(), report.to_payload())


def _report(**kwargs: Any) -> FeedRuntimeWriterLivenessReport:
    return FeedRuntimeWriterLivenessReport(
        schema_version=FEED_RUNTIME_WRITER_LIVENESS_SCHEMA_VERSION,
        source=FEED_RUNTIME_WRITER_LIVENESS_SOURCE,
        **kwargs,
    )


def _payload_or_none(value: Mapping[str, Any] | Any | None) -> dict[str, Any] | None:
    if hasattr(value, "to_payload"):
        try:
            value = value.to_payload()
        except Exception:
            return None
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _timestamp_from_keys(payload: Mapping[str, Any], keys: tuple[str, ...]) -> tuple[str | None, float | None]:
    for key in keys:
        if key not in payload:
            continue
        parsed = _timestamp_value_to_epoch(payload.get(key))
        if parsed is not None:
            return key, parsed
    return None, None


def _timestamp_value_to_epoch(value: Any) -> float | None:
    numeric = _finite_float_or_none(value)
    if numeric is not None:
        if numeric > 1_000_000_000_000:
            numeric = numeric / 1000.0
        return numeric
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _is_recovery_visible(
    failure_epoch: float | None,
    recovery_epoch: float | None,
    now_epoch: float,
    recovery_visibility_max_age_sec: float,
) -> bool:
    if failure_epoch is None:
        return True
    if recovery_epoch is None or recovery_epoch < failure_epoch:
        return False
    return now_epoch - recovery_epoch <= recovery_visibility_max_age_sec


def _first_optional_bool(payload: Mapping[str, Any], keys: tuple[str, ...]) -> bool | None:
    for key in keys:
        if key in payload:
            parsed = _optional_bool(payload.get(key))
            if parsed is not None:
                return parsed
    return None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "connected", "healthy"}:
        return True
    if text in {"false", "0", "no", "n", "disconnected", "unhealthy"}:
        return False
    return None


def _optional_int(value: Any) -> int | None:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out >= 0 else None


def _finite_float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _positive_float_or_none(value: Any) -> float | None:
    out = _finite_float_or_none(value)
    if out is None or out <= 0:
        return None
    return out


def _non_negative_float_or_none(value: Any) -> float | None:
    out = _finite_float_or_none(value)
    if out is None or out < 0:
        return None
    return out


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload["read_only"] = True
    payload["append"] = False
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload[_LIVE_ACTION_KEY] = False
    payload[_BROKER_ACTION_KEY] = False


__all__ = [
    "DEFAULT_FUTURE_SKEW_TOLERANCE_SEC",
    "DEFAULT_RECOVERY_VISIBILITY_MAX_AGE_SEC",
    "DEFAULT_WRITER_MAX_AGE_SEC",
    "FEED_RUNTIME_WRITER_LIVENESS_SCHEMA_VERSION",
    "FEED_RUNTIME_WRITER_LIVENESS_SOURCE",
    "FUTURE_HEARTBEAT_REASON",
    "FeedRuntimeWriterLivenessReport",
    "INVALID_CONFIG_REASON",
    "INVALID_SNAPSHOT_REASON",
    "MISSING_HEARTBEAT_REASON",
    "SUBSCRIPTION_RECOVERY_MISSING_REASON",
    "WEBSOCKET_RECOVERY_MISSING_REASON",
    "WRITER_FRESH_REASON",
    "WRITER_STALE_REASON",
    "WRITER_STATUS_ALIVE",
    "WRITER_STATUS_BLOCKED",
    "WRITER_STATUS_RECOVERY_MISSING",
    "WRITER_STATUS_STALE",
    "build_feed_runtime_writer_liveness_report",
    "write_feed_runtime_writer_liveness_evidence",
]

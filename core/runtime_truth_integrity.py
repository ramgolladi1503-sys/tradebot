from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Iterable, Mapping


TRUTH_CHECKSUM_VERSION = 1

_TRANSPORT_HEALTHY_STATES = {"CONNECTED"}
_TRANSPORT_UNHEALTHY_STATES = {"BLOCKED", "RECONNECTING", "DISCONNECTED"}
_FEED_TRUTH_STRICT_BLOCK_STATES = {
    "DEAD",
    "RECOVERY_BLOCKED",
    "RECONNECT_BLOCKED",
    "RESTART_REQUIRED",
    "RESTART_VERIFY_FAILED",
    "MARKET_CLOSED",
}


def canonical_json_text(payload: Any) -> str:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    except Exception:
        return json.dumps(str(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_json_hash(payload: Any) -> str:
    return sha256(canonical_json_text(payload).encode("utf-8")).hexdigest()


def truth_hash_from_mapping(payload: Mapping[str, Any] | None, *, exclude_keys: Iterable[str] = ()) -> str:
    if not isinstance(payload, Mapping):
        return ""
    excluded = {str(key) for key in exclude_keys}
    base = {str(key): value for key, value in payload.items() if str(key) not in excluded}
    return canonical_json_hash(base)


def build_transport_heartbeat(
    *,
    heartbeat_epoch: float | None,
    transport_state: Any,
    feed_truth_state: Any,
    snapshot_hash: str | None,
    reason_code: Any = None,
) -> dict[str, Any]:
    return {
        "heartbeat_epoch": float(heartbeat_epoch) if heartbeat_epoch is not None else None,
        "heartbeat_age_sec": 0.0,
        "heartbeat_source": "feed_runtime_latest",
        "transport_state": str(transport_state or "").strip().upper() or None,
        "feed_truth_state": str(feed_truth_state or "").strip().upper() or None,
        "feed_truth_reason_code": str(reason_code or "").strip().upper() or None,
        "snapshot_hash": str(snapshot_hash or "") or None,
        "checksum_version": TRUTH_CHECKSUM_VERSION,
    }


def build_truth_integrity_alerts(
    *,
    transport_state: Any,
    feed_truth_state: Any,
    snapshot_hash: str | None,
    expected_snapshot_hash: str | None,
) -> list[dict[str, Any]]:
    transport = str(transport_state or "").strip().upper()
    truth = str(feed_truth_state or "").strip().upper()
    alerts: list[dict[str, Any]] = []

    if not snapshot_hash:
        alerts.append(
            {
                "code": "SNAPSHOT_HASH_MISSING",
                "message": "Feed runtime snapshot is missing its integrity hash.",
                "details": {"transport_state": transport or None, "feed_truth_state": truth or None},
            }
        )
    elif expected_snapshot_hash and snapshot_hash != expected_snapshot_hash:
        alerts.append(
            {
                "code": "SNAPSHOT_HASH_MISMATCH",
                "message": "Feed runtime snapshot hash does not match the canonical recomputation.",
                "details": {
                    "transport_state": transport or None,
                    "feed_truth_state": truth or None,
                    "snapshot_hash": snapshot_hash,
                    "expected_snapshot_hash": expected_snapshot_hash,
                },
            }
        )

    if transport in _TRANSPORT_HEALTHY_STATES and truth in _FEED_TRUTH_STRICT_BLOCK_STATES:
        alerts.append(
            {
                "code": "TRANSPORT_FEED_TRUTH_CONFLICT",
                "message": "Transport reports healthy while feed truth is blocked or dead.",
                "details": {"transport_state": transport, "feed_truth_state": truth},
            }
        )
    if transport in _TRANSPORT_UNHEALTHY_STATES and truth == "LIVE":
        alerts.append(
            {
                "code": "TRANSPORT_FEED_TRUTH_CONFLICT",
                "message": "Transport reports unhealthy while feed truth claims LIVE.",
                "details": {"transport_state": transport, "feed_truth_state": truth},
            }
        )

    return alerts


def build_truth_integrity_payload(
    *,
    source_payload: Mapping[str, Any] | None,
    transport_state: Any,
    feed_truth_state: Any,
    reason_code: Any = None,
    heartbeat_epoch: float | None = None,
) -> dict[str, Any]:
    payload = dict(source_payload or {})
    payload_hash = truth_hash_from_mapping(
        payload,
        exclude_keys=(
            "snapshot_hash",
            "snapshot_hash_version",
            "transport_heartbeat",
            "transport_heartbeat_epoch",
            "transport_heartbeat_age_sec",
            "transport_heartbeat_source",
            "transport_heartbeat_state",
            "transport_heartbeat_reason",
            "truth_integrity",
            "truth_integrity_alerts",
            "truth_integrity_alert_count",
            "truth_integrity_status",
        ),
    )
    heartbeat = build_transport_heartbeat(
        heartbeat_epoch=heartbeat_epoch,
        transport_state=transport_state,
        feed_truth_state=feed_truth_state,
        snapshot_hash=payload_hash,
        reason_code=reason_code,
    )
    alerts = build_truth_integrity_alerts(
        transport_state=transport_state,
        feed_truth_state=feed_truth_state,
        snapshot_hash=payload_hash,
        expected_snapshot_hash=payload.get("snapshot_hash") if isinstance(payload.get("snapshot_hash"), str) else None,
    )
    return {
        "snapshot_hash_version": TRUTH_CHECKSUM_VERSION,
        "snapshot_hash": payload_hash,
        "transport_heartbeat": heartbeat,
        "transport_heartbeat_epoch": heartbeat["heartbeat_epoch"],
        "transport_heartbeat_age_sec": heartbeat["heartbeat_age_sec"],
        "transport_heartbeat_source": heartbeat["heartbeat_source"],
        "transport_heartbeat_state": heartbeat["transport_state"],
        "transport_heartbeat_reason": heartbeat.get("feed_truth_reason_code"),
        "truth_integrity_alerts": alerts,
        "truth_integrity_alert_count": len(alerts),
        "truth_integrity_status": "ALERT" if alerts else "OK",
    }


__all__ = [
    "TRUTH_CHECKSUM_VERSION",
    "build_transport_heartbeat",
    "build_truth_integrity_alerts",
    "build_truth_integrity_payload",
    "canonical_json_hash",
    "canonical_json_text",
    "truth_hash_from_mapping",
]

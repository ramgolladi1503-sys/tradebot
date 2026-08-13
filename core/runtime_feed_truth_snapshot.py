from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from config import config as cfg
from core.events import write_json_atomic_if_changed
from core.runtime_truth_integrity import build_truth_integrity_payload
from core.feed.artifact_provenance import (
    FEED_TRUTH_SCHEMA_VERSION,
    stamp_feed_truth_provenance,
)
from core.paths import logs_dir, repo_logs_dir, runtime_dir


RUNTIME_FEED_TRUTH_SNAPSHOT_SCHEMA_VERSION = FEED_TRUTH_SCHEMA_VERSION
RUNTIME_FEED_TRUTH_SNAPSHOT_SOURCE = "runtime_feed_truth_snapshot_v1"
RUNTIME_FEED_TRUTH_SNAPSHOT_FILENAME = "feed_truth_latest.json"


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _min_age(age_by_symbol: Mapping[str, Any] | None) -> float | None:
    ages: list[float] = []
    for v in dict(age_by_symbol or {}).values():
        age = _safe_float(v)
        if age is None:
            continue
        ages.append(float(age))
    return min(ages) if ages else None


def _boolish(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def build_feed_truth_snapshot(
    *,
    feed_runtime: Mapping[str, Any] | None,
    phase2_rejection: Mapping[str, Any] | None,
) -> dict[str, Any]:
    feed = _as_mapping(feed_runtime)
    phase2 = _as_mapping(phase2_rejection)

    ws_connected = _boolish(feed.get("effective_ws_connected"))
    if ws_connected is None:
        ws_connected = _boolish(feed.get("ws_connected"))

    market_open = _boolish(feed.get("market_open"))
    market_closed_detected = market_open is False

    latest_tick_age_sec = _safe_float(feed.get("last_ws_tick_age_sec"))
    if latest_tick_age_sec is None:
        latest_tick_age_sec = _safe_float(feed.get("last_tick_age_sec"))

    latest_option_tick_age_sec = _min_age(feed.get("option_last_tick_age_by_symbol"))
    subscribed_tokens_count = int(feed.get("subscribed_tokens_count") or 0)
    subscribed_option_tokens_count = int(feed.get("subscribed_option_tokens_count") or 0)

    option_sla_sec = float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0) or 2.0)
    underlying_sla_sec = float(getattr(cfg, "LTP_SLA_SECONDS", option_sla_sec) or option_sla_sec)

    underlying_tick_fresh = (
        latest_tick_age_sec is not None and float(latest_tick_age_sec) <= float(underlying_sla_sec)
    )
    option_tick_fresh = (
        latest_option_tick_age_sec is not None
        and float(latest_option_tick_age_sec) <= float(option_sla_sec)
        and subscribed_option_tokens_count > 0
    )

    last_depth_age_sec = _safe_float(feed.get("last_depth_age_sec"))
    depth_sla_sec = float(getattr(cfg, "DEPTH_SLA_SECONDS", 2.0) or 2.0)
    depth_fresh = last_depth_age_sec is not None and float(last_depth_age_sec) <= float(depth_sla_sec)

    stale_reasons: list[str] = []
    if ws_connected is not True:
        stale_reasons.append("ws_disconnected")
    if market_closed_detected:
        stale_reasons.append("market_closed")
    if not underlying_tick_fresh:
        stale_reasons.append("underlying_tick_stale_or_missing")
    if not option_tick_fresh:
        stale_reasons.append("option_tick_stale_or_missing")
    if not depth_fresh:
        stale_reasons.append("depth_stale_or_missing")

    feed_fresh = bool(ws_connected is True and (not market_closed_detected) and underlying_tick_fresh and option_tick_fresh)

    payload = {
        "schema_version": RUNTIME_FEED_TRUTH_SNAPSHOT_SCHEMA_VERSION,
        "source": RUNTIME_FEED_TRUTH_SNAPSHOT_SOURCE,
        "market_closed_detected": bool(market_closed_detected),
        "ws_connected": ws_connected,
        "feed_fresh": bool(feed_fresh),
        "underlying_tick_fresh": bool(underlying_tick_fresh),
        "option_tick_fresh": bool(option_tick_fresh),
        "depth_fresh": bool(depth_fresh),
        "latest_tick_age_sec": latest_tick_age_sec,
        "latest_option_tick_age_sec": latest_option_tick_age_sec,
        "subscribed_tokens_count": int(subscribed_tokens_count),
        "subscribed_option_tokens_count": int(subscribed_option_tokens_count),
        "selected_contract_quote_fresh": None,
        "selected_quote_age_sec": None,
        "stale_reason": stale_reasons,
        "feed_stale_hard_block_count": int(phase2.get("feed_stale_hard_block_count") or 0),
        "phase2_missing_quote_age_count": int(phase2.get("missing_quote_age_count") or 0),
        "generated_epoch": float(time.time()),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
    }
    payload = stamp_feed_truth_provenance(payload)
    payload.update(
        build_truth_integrity_payload(
            source_payload=payload,
            transport_state="CONNECTED" if ws_connected is True else "DISCONNECTED" if ws_connected is False else "UNKNOWN",
            feed_truth_state="LIVE" if feed_fresh else "DEGRADED" if ws_connected is True else "DEAD",
            reason_code="feed_fresh" if feed_fresh else "feed_stale",
            heartbeat_epoch=payload["generated_epoch"],
        )
    )
    # Ensure json-serializable primitives only.
    return json.loads(json.dumps(payload, ensure_ascii=True, default=str))


def write_feed_truth_snapshot_latest(
    *,
    payload: Mapping[str, Any],
    logs_path: Path | None = None,
    runtime_path: Path | None = None,
) -> tuple[Path, Path]:
    # Contract: write both repo-local `logs/` and runtime `.runtime/` latest artifacts.
    # For backward compatibility, also mirror into runtime `logs_dir()` (usually `.runtime/logs`).
    logs_target = Path(logs_path) if logs_path is not None else (repo_logs_dir() / RUNTIME_FEED_TRUTH_SNAPSHOT_FILENAME)
    runtime_target = Path(runtime_path) if runtime_path is not None else (runtime_dir() / RUNTIME_FEED_TRUTH_SNAPSHOT_FILENAME)
    runtime_logs_target = logs_dir() / RUNTIME_FEED_TRUTH_SNAPSHOT_FILENAME
    logs_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_logs_target.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload) if isinstance(payload, Mapping) else {}
    if bool(getattr(cfg, "RUNTIME_SNAPSHOT_WRITE_DEDUP_ENABLE", True)):
        write_json_atomic_if_changed(logs_target, out)
        write_json_atomic_if_changed(runtime_target, out)
        write_json_atomic_if_changed(runtime_logs_target, out)
    else:
        from core.events import write_json_atomic

        write_json_atomic(logs_target, out)
        write_json_atomic(runtime_target, out)
        write_json_atomic(runtime_logs_target, out)
    return logs_target, runtime_target


__all__ = [
    "RUNTIME_FEED_TRUTH_SNAPSHOT_FILENAME",
    "build_feed_truth_snapshot",
    "write_feed_truth_snapshot_latest",
]

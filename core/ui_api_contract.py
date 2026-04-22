from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.paths import logs_dir
from core.runtime_snapshot_store import (
    ADVISORY_LATEST_PATH,
    FEED_RUNTIME_LATEST_PATH,
    TOP_OPPORTUNITIES_LATEST_PATH,
    read_snapshot,
)
from core.review_queue import (
    QUEUE_PATH as REVIEW_QUEUE_PATH,
    QUICK_QUEUE_PATH as QUICK_REVIEW_QUEUE_PATH,
    SCALP_QUEUE_PATH,
    TARGET_POINTS_QUEUE_PATH,
    ZERO_HERO_QUEUE_PATH,
    load_queue_rows,
)
from dashboard.readers.advisory_reader import read_advisory_snapshot_rows


_EXECUTABLE_CLASSES = {"EXECUTABLE"}
_WATCHLIST_CLASSES = {"NEAR_EXECUTABLE", "WATCHLIST"}
_FALLBACK_PRICE_SOURCES = {"REST_FALLBACK", "LAST", "MID", "MARK", "NONE"}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _read_snapshot_payload(path: Path) -> dict[str, Any]:
    try:
        envelope = read_snapshot(path)
    except Exception:
        return {}
    payload = envelope.get("payload")
    return payload if isinstance(payload, dict) else {}


def _classify_row(row: dict[str, Any]) -> str:
    candidate_class = str(
        row.get("candidate_class")
        or row.get("candidate_status")
        or row.get("readiness")
        or "ADVISORY_ONLY"
    ).strip().upper()
    if candidate_class in _EXECUTABLE_CLASSES:
        return "EXECUTABLE"
    if candidate_class in _WATCHLIST_CLASSES:
        return "WATCHLIST"
    return "ADVISORY_ONLY"


def _is_real_executable(row: dict[str, Any]) -> bool:
    candidate_class = _classify_row(row)
    entry_status = str(row.get("entry_status") or row.get("execution_entry_status") or "").strip().upper()
    price_source = str(row.get("price_source") or row.get("entry_source") or "").strip().upper()
    if candidate_class != "EXECUTABLE":
        return False
    if price_source in _FALLBACK_PRICE_SOURCES:
        return False
    if entry_status in {"NON_EXECUTABLE", "MISSING", "STALE_OPTION_LTP", "STALE_PRICE", "INVALID_LTP"}:
        return False
    return True


def _sanitize_row(row: dict[str, Any], *, source_bucket: str | None = None) -> dict[str, Any]:
    candidate_class = _classify_row(row)
    real_executable = _is_real_executable(row)
    price_source = str(row.get("price_source") or row.get("entry_source") or "").strip().upper() or None
    entry_status = str(row.get("entry_status") or row.get("execution_entry_status") or "").strip().upper() or None
    return {
        "trade_id": row.get("trade_id") or row.get("advisory_id") or row.get("trade_key"),
        "trade_key": row.get("trade_key") or row.get("advisory_id") or row.get("trade_id"),
        "symbol": row.get("symbol"),
        "tradingsymbol": row.get("tradingsymbol"),
        "option_type": row.get("option_type") or row.get("type"),
        "strike": row.get("strike"),
        "expiry": row.get("expiry_date") or row.get("expiry"),
        "side": row.get("side"),
        "status": row.get("status"),
        "candidate_class": candidate_class,
        "entry_status": entry_status,
        "price_source": price_source,
        "real_executable": bool(real_executable),
        "permission": row.get("permission"),
        "entry": _safe_float(row.get("entry")),
        "stop": _safe_float(row.get("stop") or row.get("stop_loss")),
        "target": _safe_float(row.get("target")),
        "confidence": _safe_float(
            row.get("confidence_final")
            or row.get("global_confidence")
            or row.get("global_conf")
            or row.get("confidence")
        ),
        "ltp": _safe_float(row.get("ltp") or row.get("opt_ltp") or row.get("current_ltp")),
        "bid": _safe_float(row.get("bid") or row.get("opt_bid")),
        "ask": _safe_float(row.get("ask") or row.get("opt_ask")),
        "mark_price": _safe_float(row.get("mark_price")),
        "quote_age_sec": _safe_float(row.get("quote_age_sec") or row.get("price_age_sec")),
        "spread_pct": _safe_float(row.get("spread_pct")),
        "primary_blocker": row.get("primary_blocker") or row.get("final_blocker") or row.get("entry_block_reason"),
        "source_bucket": source_bucket or row.get("source_bucket"),
        "timestamp": row.get("display_ts_ist") or row.get("timestamp") or row.get("timestamp_utc_iso"),
    }


def _sanitize_rows(rows: list[dict[str, Any]], *, source_bucket: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(_sanitize_row(row, source_bucket=source_bucket))
    return out


def _partition_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    executable: list[dict[str, Any]] = []
    watchlist: list[dict[str, Any]] = []
    advisory: list[dict[str, Any]] = []
    for row in rows:
        if bool(row.get("real_executable")):
            executable.append(row)
        elif str(row.get("candidate_class") or "") == "WATCHLIST":
            watchlist.append(row)
        else:
            advisory.append(row)
    return {
        "executable": executable,
        "watchlist": watchlist,
        "advisory": advisory,
    }


def get_top_opportunities_payload(*, limit: int = 5) -> dict[str, Any]:
    payload = _read_snapshot_payload(TOP_OPPORTUNITIES_LATEST_PATH)
    raw_rows: list[dict[str, Any]] = []
    for key in ("top_executable_opportunities", "top_advisory_opportunities"):
        values = payload.get(key)
        if isinstance(values, list):
            raw_rows.extend([row for row in values if isinstance(row, dict)])
    sanitized = _sanitize_rows(raw_rows)
    partitions = _partition_rows(sanitized)
    return {
        "source": str(TOP_OPPORTUNITIES_LATEST_PATH),
        "generated_at": payload.get("generated_at"),
        "executable": partitions["executable"][: max(1, int(limit))],
        "watchlist": partitions["watchlist"][: max(1, int(limit))],
        "advisory": partitions["advisory"][: max(1, int(limit))],
    }


def get_advisory_payload(*, limit: int = 25) -> dict[str, Any]:
    snapshot = read_advisory_snapshot_rows(ADVISORY_LATEST_PATH, limit=max(1, int(limit)))
    rows = _sanitize_rows(list(snapshot.get("rows") or []), source_bucket="advisory_snapshot")
    partitions = _partition_rows(rows)
    return {
        "state": snapshot.get("state"),
        "source": snapshot.get("path"),
        "errors": list(snapshot.get("errors") or []),
        "executable": partitions["executable"],
        "watchlist": partitions["watchlist"],
        "advisory": partitions["advisory"],
    }


def get_review_queue_payload(*, limit: int = 50) -> dict[str, Any]:
    queue_defs = [
        ("review_queue", REVIEW_QUEUE_PATH),
        ("quick_queue", QUICK_REVIEW_QUEUE_PATH),
        ("target_points", TARGET_POINTS_QUEUE_PATH),
        ("zero_to_hero", ZERO_HERO_QUEUE_PATH),
        ("scalp_queue", SCALP_QUEUE_PATH),
    ]
    items: list[dict[str, Any]] = []
    for source_bucket, path in queue_defs:
        try:
            rows = load_queue_rows(Path(path))
        except Exception:
            rows = []
        items.extend(_sanitize_rows(list(rows)[: max(1, int(limit))], source_bucket=source_bucket))
    return {
        "count": len(items),
        "items": items[: max(1, int(limit))],
    }


def get_system_health_payload() -> dict[str, Any]:
    feed_runtime = _read_snapshot_payload(FEED_RUNTIME_LATEST_PATH)
    runtime_health = _load_json_file(logs_dir() / "runtime_health_latest.json")
    feed_section = runtime_health.get("feed") if isinstance(runtime_health.get("feed"), dict) else {}
    return {
        "market_open": runtime_health.get("market_open"),
        "mode": runtime_health.get("mode"),
        "feed_runtime": {
            "state": feed_section.get("runtime_state") or feed_runtime.get("state"),
            "ws_connected": feed_section.get("ws_connected"),
            "last_tick_age_sec": feed_section.get("last_tick_age_sec"),
            "depth_age_sec": feed_section.get("depth_age_sec"),
            "subscriptions_count": feed_section.get("subscriptions_count"),
            "intended_tokens_count": feed_section.get("intended_tokens_count"),
            "last_error": feed_section.get("last_error"),
        },
    }


def get_axiom_home_payload(*, limit: int = 5) -> dict[str, Any]:
    top = get_top_opportunities_payload(limit=limit)
    advisory = get_advisory_payload(limit=max(limit * 3, 15))
    review = get_review_queue_payload(limit=max(limit * 5, 25))
    health = get_system_health_payload()
    return {
        "top_opportunities": top,
        "advisory": advisory,
        "review_queue": review,
        "system_health": health,
    }

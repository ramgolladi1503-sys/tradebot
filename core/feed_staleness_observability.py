"""Read-only feed and staleness observability collector.

This module intentionally does not change execution gates, broker behavior,
depth subscription behavior, ranking, or suggestions. It only reads runtime
status files and produces a compact evidence report that explains feed health,
staleness, depth subscription state, and executable blockers.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from core.paths import logs_dir as default_logs_dir

DEFAULT_RUNTIME_LOG_FILES = {
    "feed_runtime": "feed_runtime_latest.json",
    "runtime_health": "runtime_health_latest.json",
    "engine_cycle": "engine_cycle_status.json",
    "suggestions_status": "suggestions_status.json",
}

DEFAULT_SUGGESTIONS_JSONL = "suggestions.jsonl"
DEFAULT_EVENTS_JSONL = "events.jsonl"

STALE_KEY_HINTS = (
    "stale",
    "age",
    "feed_stale",
    "stale_option",
    "stale_ltp",
    "option_ltp_age",
    "ltp_age",
)

BLOCKER_KEY_HINTS = (
    "blocker",
    "blockers",
    "block_reason",
    "block_reasons",
    "primary_blocker",
    "reason",
    "reasons",
)

EXECUTABLE_HINTS = (
    "EXECUTE",
    "EXECUTABLE",
    "execution_allowed",
    "visible_executable_count",
)


def _resolve_logs_dir(log_root: str | Path | None = None) -> Path:
    if log_root is None:
        return default_logs_dir()
    return Path(log_root).expanduser()


def _safe_json_load(path: Path) -> dict[str, Any]:
    try:
        if not path.exists() or not path.is_file():
            return {"_missing": True, "_path": str(path)}
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return {"_empty": True, "_path": str(path)}
        data = json.loads(raw)
        if isinstance(data, dict):
            data.setdefault("_path", str(path))
            return data
        return {"_value": data, "_path": str(path)}
    except Exception as exc:  # pragma: no cover - defensive runtime evidence path
        return {"_error": str(exc), "_path": str(path)}


def _safe_jsonl_tail(path: Path, *, limit: int = 200) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    for line in lines[-max(1, int(limit)) :]:
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _get_nested(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        cur: Any = data
        ok = True
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok:
            return cur
    return default


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "ok", "connected"}:
        return True
    if text in {"false", "0", "no", "n", "bad", "degraded", "disconnected"}:
        return False
    return None


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if out != out:
        return None
    return out


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _collect_key_values(data: Any, *, hints: tuple[str, ...], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            lower = path.lower()
            if any(hint in lower for hint in hints):
                out[path] = value
            if isinstance(value, (dict, list)):
                out.update(_collect_key_values(value, hints=hints, prefix=path))
    elif isinstance(data, list):
        for idx, value in enumerate(data[:50]):
            path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            if isinstance(value, (dict, list)):
                out.update(_collect_key_values(value, hints=hints, prefix=path))
    return out


def _count_blockers(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        values: list[Any] = []
        for key in (
            "primary_blocker",
            "blocker",
            "block_reason",
            "status_reason",
            "execution_blocker",
            "execution_blockers",
            "blockers",
            "block_reasons",
            "reasons",
        ):
            if key in row:
                values.append(row.get(key))
        for value in values:
            items = value if isinstance(value, list) else [value]
            for item in items:
                text = str(item or "").strip()
                if not text or text.lower() in {"none", "nan", "null"}:
                    continue
                counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _count_statuses(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = (
            row.get("execution_status")
            or row.get("candidate_status")
            or row.get("status")
            or row.get("permission")
            or row.get("decision")
        )
        text = str(value or "UNKNOWN").strip() or "UNKNOWN"
        counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _latest_numeric_age(rows: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in rows[-100:]:
        for key, value in row.items():
            lower = str(key).lower()
            if "age" not in lower and "stale" not in lower:
                continue
            number = _as_float(value)
            if number is None:
                continue
            result[str(key)] = max(result.get(str(key), 0.0), number)
    return dict(sorted(result.items()))


def build_feed_staleness_report(log_root: str | Path | None = None) -> dict[str, Any]:
    """Build a read-only feed/staleness evidence report from runtime logs."""

    root = _resolve_logs_dir(log_root)
    files = {name: _safe_json_load(root / filename) for name, filename in DEFAULT_RUNTIME_LOG_FILES.items()}
    suggestions_rows = _safe_jsonl_tail(root / DEFAULT_SUGGESTIONS_JSONL)
    events_rows = _safe_jsonl_tail(root / DEFAULT_EVENTS_JSONL)

    feed_runtime = files["feed_runtime"]
    runtime_health = files["runtime_health"]
    engine_cycle = files["engine_cycle"]
    suggestions_status = files["suggestions_status"]

    feed_ok = _as_bool(
        _get_nested(
            feed_runtime,
            "feed_ok",
            "ok",
            "status.feed_ok",
            default=_get_nested(runtime_health, "feed_ok", "status.feed_ok"),
        )
    )
    ws_connected = _as_bool(
        _get_nested(
            feed_runtime,
            "ws_connected",
            "websocket_connected",
            "connected",
            "status.ws_connected",
            default=_get_nested(runtime_health, "ws_connected", "websocket_connected"),
        )
    )

    subscribed_option_tokens_count = _as_int(
        _get_nested(
            feed_runtime,
            "subscribed_option_tokens_count",
            "option_tokens_count",
            "depth.subscribed_option_tokens_count",
            default=_get_nested(engine_cycle, "subscribed_option_tokens_count", "option_tokens_count"),
        )
    )

    visible_executable_count = _as_int(
        _get_nested(
            engine_cycle,
            "visible_executable_count",
            "executable_count",
            default=_get_nested(suggestions_status, "visible_executable_count", "executable_count"),
        )
    )

    stale_evidence = {
        "feed_runtime": _collect_key_values(feed_runtime, hints=STALE_KEY_HINTS),
        "runtime_health": _collect_key_values(runtime_health, hints=STALE_KEY_HINTS),
        "engine_cycle": _collect_key_values(engine_cycle, hints=STALE_KEY_HINTS),
        "suggestions_status": _collect_key_values(suggestions_status, hints=STALE_KEY_HINTS),
        "suggestions_tail_max_ages": _latest_numeric_age(suggestions_rows),
        "events_tail_max_ages": _latest_numeric_age(events_rows),
    }

    blocker_evidence = {
        "runtime_health": _collect_key_values(runtime_health, hints=BLOCKER_KEY_HINTS),
        "engine_cycle": _collect_key_values(engine_cycle, hints=BLOCKER_KEY_HINTS),
        "suggestions_status": _collect_key_values(suggestions_status, hints=BLOCKER_KEY_HINTS),
        "suggestions_tail_blocker_counts": _count_blockers(suggestions_rows),
        "events_tail_blocker_counts": _count_blockers(events_rows),
    }

    status_counts = {
        "suggestions_tail_status_counts": _count_statuses(suggestions_rows),
        "events_tail_status_counts": _count_statuses(events_rows),
    }

    missing_files = [name for name, data in files.items() if data.get("_missing")]
    errored_files = {name: data.get("_error") for name, data in files.items() if data.get("_error")}

    report = {
        "schema_version": 1,
        "generated_epoch": time.time(),
        "logs_dir": str(root),
        "read_only": True,
        "is_order_action": False,
        "summary": {
            "feed_ok": feed_ok,
            "ws_connected": ws_connected,
            "subscribed_option_tokens_count": subscribed_option_tokens_count,
            "visible_executable_count": visible_executable_count,
            "suggestions_tail_rows": len(suggestions_rows),
            "events_tail_rows": len(events_rows),
            "missing_runtime_files": missing_files,
            "errored_runtime_files": errored_files,
        },
        "stale_evidence": stale_evidence,
        "blocker_evidence": blocker_evidence,
        "status_counts": status_counts,
        "source_files": {name: data.get("_path") for name, data in files.items()},
    }
    return report


def write_feed_staleness_report(
    log_root: str | Path | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """Write the read-only evidence report as JSON and return its path."""

    root = _resolve_logs_dir(log_root)
    out = Path(output_path) if output_path is not None else root / "feed_staleness_observability_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    report = build_feed_staleness_report(root)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(out)
    return out


__all__ = ["build_feed_staleness_report", "write_feed_staleness_report"]

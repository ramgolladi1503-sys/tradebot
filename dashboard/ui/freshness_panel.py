from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from core.runtime_snapshot_store import read_snapshot_with_freshness


STALE_STATUSES = {"stale", "missing", "invalid", "future_timestamp", "unknown_timestamp"}
WARNING_STATUSES = {"unknown", "unknown_timestamp"}


def collect_latest_artifact_freshness_rows(
    artifacts: Mapping[str, str | Path],
    *,
    reader: Callable[..., Mapping[str, Any]] = read_snapshot_with_freshness,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, path in artifacts.items():
        try:
            result = reader(path, artifact_name=str(label))
        except Exception as exc:
            result = {
                "fresh": False,
                "freshness": {
                    "artifact_name": str(label),
                    "path": str(path),
                    "status": "invalid",
                    "age_seconds": None,
                    "timestamp_source": None,
                    "reasons": [f"freshness_reader_error:{type(exc).__name__}"],
                },
                "blockers": [f"freshness_reader_error:{type(exc).__name__}"],
            }
        rows.append(build_freshness_panel_row(str(label), result))
    return rows


def build_freshness_panel_row(label: str, result: Mapping[str, Any]) -> dict[str, Any]:
    freshness = result.get("freshness") if isinstance(result, Mapping) else None
    if not isinstance(freshness, Mapping):
        freshness = {}
    blockers = result.get("blockers") if isinstance(result, Mapping) else []
    if not isinstance(blockers, list):
        blockers = []
    status = str(freshness.get("status") or "unknown").strip().lower() or "unknown"
    fresh = bool(result.get("fresh")) if isinstance(result, Mapping) else False
    age_seconds = freshness.get("age_seconds")
    return {
        "artifact": str(label),
        "status": status,
        "fresh": fresh,
        "severity": _freshness_severity(status=status, fresh=fresh),
        "age": _format_age(age_seconds),
        "timestamp_source": freshness.get("timestamp_source") or "n/a",
        "blockers": ", ".join(str(item) for item in blockers if str(item).strip()) or "none",
        "path": freshness.get("path") or "",
    }


def summarize_freshness_panel_rows(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    total = len(rows)
    fresh_count = sum(1 for row in rows if bool(row.get("fresh")))
    stale_count = sum(1 for row in rows if str(row.get("severity") or "").lower() == "error")
    warning_count = sum(1 for row in rows if str(row.get("severity") or "").lower() == "warning")
    return {
        "total": total,
        "fresh": fresh_count,
        "warning": warning_count,
        "stale": stale_count,
        "not_fresh": max(0, total - fresh_count),
    }


def render_latest_artifact_freshness_panel(
    st_module: Any,
    rows: list[Mapping[str, Any]],
    *,
    title: str = "Latest Artifact Freshness",
) -> dict[str, int]:
    summary = summarize_freshness_panel_rows(rows)
    st_module.markdown(f"### {title}")
    if not rows:
        st_module.caption("No latest artifact freshness rows available.")
        return summary
    if summary["stale"] > 0:
        st_module.error(
            f"{summary['not_fresh']} of {summary['total']} latest artifacts are not fresh."
        )
    elif summary["warning"] > 0:
        st_module.warning(
            f"{summary['warning']} latest artifacts need timestamp review."
        )
    else:
        st_module.success(f"All {summary['fresh']} latest artifacts are fresh.")
    st_module.dataframe(
        [dict(row) for row in rows],
        use_container_width=True,
        hide_index=True,
    )
    return summary


def _freshness_severity(*, status: str, fresh: bool) -> str:
    if fresh and status == "fresh":
        return "ok"
    if status in WARNING_STATUSES:
        return "warning"
    if status in STALE_STATUSES:
        return "error"
    return "warning"


def _format_age(value: Any) -> str:
    try:
        if value is None:
            return "n/a"
        seconds = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if seconds < 0:
        return f"{seconds:.1f}s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60.0
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours = minutes / 60.0
    return f"{hours:.1f}h"


__all__ = [
    "build_freshness_panel_row",
    "collect_latest_artifact_freshness_rows",
    "render_latest_artifact_freshness_panel",
    "summarize_freshness_panel_rows",
]

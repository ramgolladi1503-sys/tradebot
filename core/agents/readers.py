from __future__ import annotations

from collections import deque
import json
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from core.paths import logs_dir, runtime_dir


def _safe_read_text(path: Path | None, *, tail_lines: int | None = None) -> str:
    if path is None or not path.exists() or not path.is_file():
        return ""
    if tail_lines is None or tail_lines <= 0:
        return path.read_text(encoding="utf-8", errors="replace")
    buffer: deque[str] = deque(maxlen=tail_lines)
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            buffer.append(line.rstrip("\n"))
    return "\n".join(buffer)


def read_json_file(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_jsonl_file(path: Path | None, *, tail_lines: int | None = None) -> list[dict[str, Any]]:
    text = _safe_read_text(path, tail_lines=tail_lines)
    if not text:
        return []
    rows: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            try:
                payload = json.loads(line[line.find("{") : line.rfind("}") + 1]) if "{" in line and "}" in line else None
            except Exception:
                payload = None
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def discover_latest_existing_path(candidates: Sequence[Path]) -> Path | None:
    existing = [path for path in candidates if path.exists() and path.is_file()]
    if not existing:
        return None
    return sorted(existing, key=lambda item: (item.stat().st_mtime, str(item)))[-1]


def discover_runtime_artifacts(
    *,
    runtime_root: Path | None = None,
    logs_root: Path | None = None,
    session_root: Path | None = None,
) -> dict[str, Path | None]:
    runtime_root = Path(runtime_root) if runtime_root is not None else runtime_dir()
    logs_root = Path(logs_root) if logs_root is not None else logs_dir()
    session_root = Path(session_root) if session_root is not None else runtime_root / "live_sessions"

    live_sessions = []
    if session_root.exists():
        live_sessions = sorted(
            (path for path in session_root.glob("*") if path.is_dir()),
            key=lambda item: (item.stat().st_mtime, str(item)),
        )

    return {
        "feed_runtime_runtime_logs": discover_latest_existing_path(
            [
                runtime_root / "logs" / "feed_runtime_latest.json",
                runtime_root / "feed_runtime_latest.json",
                logs_root / "feed_runtime_latest.json",
                *(session / "feed_runtime_latest.json" for session in live_sessions),
            ]
        ),
        "feed_runtime_runtime": discover_latest_existing_path(
            [
                runtime_root / "feed_runtime_latest.json",
                logs_root / "feed_runtime_latest.json",
                *(session / "feed_runtime_latest.json" for session in live_sessions),
            ]
        ),
        "feed_runtime_logs": discover_latest_existing_path(
            [
                logs_root / "feed_runtime_latest.json",
                *(session / "feed_runtime_latest.json" for session in live_sessions),
            ]
        ),
        "depth_ws_watchdog": discover_latest_existing_path(
            [
                runtime_root / "logs" / "depth_ws_watchdog.log",
                logs_root / "watchdog.log",
            ]
        ),
        "ranked_pipeline_runtime": discover_latest_existing_path(
            [
                logs_root / "ranked_pipeline_runtime_latest.json",
                runtime_root / "logs" / "ranked_pipeline_runtime_latest.json",
            ]
        ),
        "candidate_starvation_trace": discover_latest_existing_path(
            [
                logs_root / "candidate_starvation_trace_latest.json",
                runtime_root / "logs" / "candidate_starvation_trace_latest.json",
            ]
        ),
    }


def grep_lines(
    *,
    paths: Iterable[Path | None],
    patterns: Sequence[str],
    tail_lines: int | None = None,
) -> list[dict[str, Any]]:
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns if pattern]
    matches: list[dict[str, Any]] = []
    for path in paths:
        if path is None:
            continue
        text = _safe_read_text(path, tail_lines=tail_lines)
        if not text:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not any(pattern.search(line) for pattern in compiled):
                continue
            matches.append(
                {
                    "source_path": str(path),
                    "line_number": line_number,
                    "excerpt": line.strip(),
                }
            )
    return matches

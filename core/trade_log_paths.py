from __future__ import annotations

# Migration note:
# Canonical helper name is ensure_trade_log_exists(); ensure_trade_log_file() kept for compatibility.

from pathlib import Path

from config import config as cfg
from core.paths import logs_dir, data_root


def _kind_filename(kind: str) -> str:
    key = str(kind or "trade_log").strip().lower()
    if key in {"trade_updates", "updates", "trade_update"}:
        return "trade_updates.jsonl"
    return "trade_log.jsonl"


def _looks_like_path(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return any(ch in text for ch in ("/", "\\", ".json", ".jsonl", ".csv"))


def _configured_trade_log_path(kind: str, desk_id: str) -> Path:
    key = "TRADE_UPDATES_PATH" if _kind_filename(kind) == "trade_updates.jsonl" else "TRADE_LOG_PATH"
    raw = str(getattr(cfg, key, "") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return logs_dir() / _kind_filename(kind)


def _legacy_trade_log_paths(kind: str) -> list[Path]:
    filename = _kind_filename(kind)
    if filename == "trade_updates.jsonl":
        return [
            data_root() / "trade_updates.json",
            Path("trade_updates.json"),
            logs_dir() / "trade_updates.json",
        ]
    return [
        data_root() / "trade_log.json",
        Path("trade_log.json"),
        logs_dir() / "trade_log.json",
    ]


def resolve_trade_log_path(
    desk_id: str | Path | None = None,
    kind: str = "trade_log",
    path: str | Path | None = None,
) -> Path:
    # Backward compatibility: old signature resolve_trade_log_path(path)
    if path is None and desk_id is not None and _looks_like_path(desk_id):
        path = desk_id
        desk_id = None
    if path is not None and str(path).strip():
        return Path(str(path)).expanduser()

    desk = str(desk_id or getattr(cfg, "DESK_ID", "DEFAULT")).strip() or "DEFAULT"
    primary = _configured_trade_log_path(kind, desk)
    candidates: list[Path] = [primary]
    for legacy in _legacy_trade_log_paths(kind):
        if legacy not in candidates:
            candidates.append(legacy)

    for cand in candidates:
        try:
            if cand.exists() and cand.is_file() and cand.stat().st_size > 0:
                return cand
        except Exception:
            continue
    for cand in candidates:
        try:
            if cand.exists() and cand.is_file():
                return cand
        except Exception:
            continue
    return primary


def ensure_trade_log_file(
    desk_id: str | Path | None = None,
    kind: str = "trade_log",
    path: str | Path | None = None,
    *,
    create_if_missing: bool = True,
) -> Path:
    resolved = resolve_trade_log_path(desk_id=desk_id, kind=kind, path=path)
    if create_if_missing:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        if not resolved.exists():
            resolved.touch()
    return resolved


def ensure_trade_log_exists(
    desk_id: str | Path | None = None,
    kind: str = "trade_log",
    path: str | Path | None = None,
) -> Path:
    return ensure_trade_log_file(desk_id=desk_id, kind=kind, path=path, create_if_missing=True)

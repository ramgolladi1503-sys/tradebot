from __future__ import annotations

# Migration note:
# Canonical helper name is ensure_trade_log_exists(); ensure_trade_log_file() kept for compatibility.

from pathlib import Path

from config import config as cfg


def _legacy_trade_log_paths() -> list[Path]:
    return [
        Path("data/trade_log.json"),
        Path("trade_log.json"),
        Path("logs/trade_log.json"),
    ]


def configured_trade_log_path() -> Path:
    raw = str(getattr(cfg, "TRADE_LOG_PATH", "logs/trade_log.jsonl") or "").strip()
    if not raw:
        raw = "logs/trade_log.jsonl"
    return Path(raw)


def resolve_trade_log_path(path: str | Path | None = None) -> Path:
    if path is not None and str(path).strip():
        return Path(str(path))

    primary = configured_trade_log_path()
    candidates: list[Path] = [primary]
    for legacy in _legacy_trade_log_paths():
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


def ensure_trade_log_file(path: str | Path | None = None, *, create_if_missing: bool = True) -> Path:
    resolved = resolve_trade_log_path(path)
    if create_if_missing:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        if not resolved.exists():
            resolved.touch()
    return resolved


def ensure_trade_log_exists(path: str | Path | None = None) -> Path:
    return ensure_trade_log_file(path, create_if_missing=True)

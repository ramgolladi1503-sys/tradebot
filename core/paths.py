from __future__ import annotations

import os
from pathlib import Path

from core.runtime_paths import DATA_ROOT, DB_ROOT, DESKS_ROOT, LOCKS_ROOT, LOGS_ROOT, REPORTS_ROOT


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def repo_logs_dir() -> Path:
    """Repository-local logs directory.

    This is intentionally distinct from logs_dir(), which defaults to DATA_ROOT/logs
    (typically `.runtime/logs`). Repo-local `logs/` is used for operator-friendly
    smoke checks and CI artifact expectations.
    """
    override = os.getenv("REPO_LOG_DIR")
    if override:
        return Path(override).expanduser()
    return repo_root() / "logs"


def ensure_dir(path: Path | str) -> Path:
    target = Path(path).expanduser()
    if target.exists() and not target.is_dir():
        raise NotADirectoryError(f"path_exists_as_file:{target}")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _cfg_path(attr: str) -> Path | None:
    # Late import keeps config/paths dependency acyclic and test-friendly.
    try:
        from config import config as cfg

        raw = str(getattr(cfg, attr, "") or "").strip()
        if raw:
            return Path(raw).expanduser()
    except Exception:
        return None
    return None


def runtime_dir() -> Path:
    # TRADEBOT_RUNTIME_ROOT is the canonical live authority and must win over
    # import-time config values and source-checkout fallback paths.
    override = os.getenv("TRADEBOT_RUNTIME_ROOT")
    if override:
        from core.runtime_paths import resolve_data_root
        return resolve_data_root(canonical_live=_canonical_live_mode())
    override = os.getenv("DATA_ROOT")
    if override:
        return Path(override).expanduser()
    return _cfg_path("DATA_ROOT") or DATA_ROOT


def _canonical_live_mode() -> bool:
    return str(os.getenv("TRADEBOT_CANONICAL_LIVE", "")).strip().lower() in {"1", "true", "yes", "on"}


def logs_dir() -> Path:
    if os.getenv("TRADEBOT_RUNTIME_ROOT"):
        return runtime_dir() / "logs"
    override = os.getenv("LOG_DIR")
    if override:
        return Path(override).expanduser()
    return _cfg_path("LOGS_ROOT") or (runtime_dir() / "logs")


def data_root() -> Path:
    return runtime_dir()


def desks_dir(desk_id: str | None = None) -> Path:
    if os.getenv("TRADEBOT_RUNTIME_ROOT"):
        base = runtime_dir() / "desks"
        return base if desk_id is None else base / str(desk_id)
    base = _cfg_path("DESKS_ROOT") or (runtime_dir() / "desks")
    if desk_id is None:
        return base
    return base / str(desk_id)


def reports_dir() -> Path:
    if os.getenv("TRADEBOT_RUNTIME_ROOT"):
        return runtime_dir() / "reports"
    return _cfg_path("REPORTS_ROOT") or (runtime_dir() / "reports")


def locks_dir() -> Path:
    if os.getenv("TRADEBOT_RUNTIME_ROOT"):
        return runtime_dir() / "locks"
    return _cfg_path("LOCKS_ROOT") or (runtime_dir() / "locks")


def db_dir() -> Path:
    if os.getenv("TRADEBOT_RUNTIME_ROOT"):
        return runtime_dir() / "db"
    return _cfg_path("DB_ROOT") or (runtime_dir() / "db")


def desk_logs_dir(desk_id: str) -> Path:
    return logs_dir() / "desks" / str(desk_id)


def regime_runtime_evidence_path() -> Path:
    """Return the governed, ignored path for runtime regime evidence."""
    return runtime_dir() / "strategy_validation" / "regime_timeline.jsonl"


def trade_db_path(desk_id: str) -> Path:
    return db_dir() / f"{str(desk_id)}.sqlite"

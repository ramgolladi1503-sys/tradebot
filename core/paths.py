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
    override = os.getenv("DATA_ROOT")
    if override:
        return Path(override).expanduser()
    return _cfg_path("DATA_ROOT") or DATA_ROOT


def logs_dir() -> Path:
    override = os.getenv("LOG_DIR")
    if override:
        return Path(override).expanduser()
    return _cfg_path("LOGS_ROOT") or (runtime_dir() / "logs")


def data_root() -> Path:
    return runtime_dir()


def desks_dir(desk_id: str | None = None) -> Path:
    base = _cfg_path("DESKS_ROOT") or (runtime_dir() / "desks")
    if desk_id is None:
        return base
    return base / str(desk_id)


def reports_dir() -> Path:
    return _cfg_path("REPORTS_ROOT") or (runtime_dir() / "reports")


def locks_dir() -> Path:
    return _cfg_path("LOCKS_ROOT") or (runtime_dir() / "locks")


def db_dir() -> Path:
    return _cfg_path("DB_ROOT") or (runtime_dir() / "db")


def desk_logs_dir(desk_id: str) -> Path:
    return logs_dir() / "desks" / str(desk_id)


def regime_runtime_evidence_path() -> Path:
    """Return the governed, ignored path for runtime regime evidence."""
    return runtime_dir() / "strategy_validation" / "regime_timeline.jsonl"


def trade_db_path(desk_id: str) -> Path:
    return db_dir() / f"{str(desk_id)}.sqlite"

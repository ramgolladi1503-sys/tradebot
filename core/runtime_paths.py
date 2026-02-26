from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_data_root() -> Path:
    raw = str(os.getenv("DATA_ROOT", "")).strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (_repo_root() / ".runtime").resolve()


DATA_ROOT: Path = _resolve_data_root()
DESKS_ROOT: Path = DATA_ROOT / "desks"
LOGS_ROOT: Path = DATA_ROOT / "logs"
REPORTS_ROOT: Path = DATA_ROOT / "reports"
LOCKS_ROOT: Path = DATA_ROOT / "locks"
DB_ROOT: Path = DATA_ROOT / "db"


def desk_data_root(desk_id: str) -> Path:
    return DESKS_ROOT / str(desk_id)


def desk_logs_root(desk_id: str) -> Path:
    return LOGS_ROOT / "desks" / str(desk_id)

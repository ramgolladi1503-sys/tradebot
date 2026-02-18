from __future__ import annotations

import os
from pathlib import Path

from core.runtime_paths import DATA_ROOT, DB_ROOT, LOCKS_ROOT, LOGS_ROOT, REPORTS_ROOT


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def logs_dir() -> Path:
    override = os.getenv("LOG_DIR")
    if override:
        return Path(override).expanduser()
    return LOGS_ROOT


def data_root() -> Path:
    return DATA_ROOT


def reports_dir() -> Path:
    return REPORTS_ROOT


def locks_dir() -> Path:
    return LOCKS_ROOT


def db_dir() -> Path:
    return DB_ROOT

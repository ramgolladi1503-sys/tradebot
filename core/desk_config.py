from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config import config as cfg
from core.runtime_paths import DB_ROOT, DESKS_ROOT, LOGS_ROOT


@dataclass(frozen=True)
class DeskConfig:
    desk_id: str
    data_dir: Path
    log_dir: Path
    trade_db_path: Path
    decision_log_path: Path
    audit_log_path: Path
    incidents_log_path: Path


def get_desk_config() -> DeskConfig:
    desk_id = getattr(cfg, "DESK_ID", "DEFAULT")
    default_data_dir = DESKS_ROOT / desk_id
    default_log_dir = LOGS_ROOT / "desks" / desk_id
    default_db_path = DB_ROOT / f"{desk_id}.sqlite"
    return DeskConfig(
        desk_id=desk_id,
        data_dir=Path(getattr(cfg, "DESK_DATA_DIR", str(default_data_dir))),
        log_dir=Path(getattr(cfg, "DESK_LOG_DIR", str(default_log_dir))),
        trade_db_path=Path(getattr(cfg, "TRADE_DB_PATH", str(default_db_path))),
        decision_log_path=Path(getattr(cfg, "DECISION_LOG_PATH", str(default_log_dir / "decision_events.jsonl"))),
        audit_log_path=Path(getattr(cfg, "AUDIT_LOG_PATH", str(default_log_dir / "audit_log.jsonl"))),
        incidents_log_path=Path(getattr(cfg, "INCIDENTS_LOG_PATH", str(default_log_dir / "incidents.jsonl"))),
    )

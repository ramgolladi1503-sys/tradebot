from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config import config as cfg


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
    return DeskConfig(
        desk_id=getattr(cfg, "DESK_ID", "DEFAULT"),
        data_dir=Path(getattr(cfg, "DESK_DATA_DIR", "data/desks/DEFAULT")),
        log_dir=Path(getattr(cfg, "DESK_LOG_DIR", "logs/desks/DEFAULT")),
        trade_db_path=Path(getattr(cfg, "TRADE_DB_PATH", "data/trades.db")),
        decision_log_path=Path(getattr(cfg, "DECISION_LOG_PATH", "logs/decision_events.jsonl")),
        audit_log_path=Path(getattr(cfg, "AUDIT_LOG_PATH", "logs/audit_log.jsonl")),
        incidents_log_path=Path(getattr(cfg, "INCIDENTS_LOG_PATH", "logs/incidents.jsonl")),
    )

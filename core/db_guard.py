import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

from config import config as cfg
from core import risk_halt
from core.paths import logs_dir
from core.time_utils import now_utc_epoch, now_ist


def _record_startup_boundary(event: str, *, details: dict[str, Any] | None = None, error: str | None = None) -> None:
    try:
        from core.runtime_startup_lifecycle import record_runtime_startup_event

        payload = {"is_order_action": False}
        if details:
            payload.update(dict(details))
        record_runtime_startup_event(
            event,
            source="core.db_guard.ensure_db_ready",
            details=payload,
            error=error,
        )
    except Exception:
        pass


def _log_event(payload: Dict[str, Any]) -> None:
    try:
        out = logs_dir() / "db_probe.jsonl"
        out.parent.mkdir(exist_ok=True)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def normalize_db_path(raw_path: str) -> Path:
    expanded = os.path.expanduser(raw_path)
    return Path(expanded).resolve()


def _ensure_permissions(db_path: Path) -> None:
    parent = db_path.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(parent, 0o700)
    except Exception:
        pass
    if not db_path.exists():
        db_path.open("a").close()
    try:
        os.chmod(db_path, 0o600)
    except Exception:
        pass


def probe_db_write(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path), timeout=5)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS __db_probe("
            "id INTEGER PRIMARY KEY, "
            "ts_epoch REAL NOT NULL)"
        )
        ts = time.time()
        cur = con.execute("INSERT INTO __db_probe(ts_epoch) VALUES (?)", (ts,))
        row_id = cur.lastrowid
        if row_id is None:
            raise RuntimeError("db_probe_insert_failed:no_rowid")
        con.execute("DELETE FROM __db_probe WHERE id = ?", (row_id,))
        con.commit()
    finally:
        con.close()


def ensure_db_ready(db_path: Optional[str] = None) -> Dict[str, Any]:
    _record_startup_boundary("DB_READY_CALLING")
    raw_path = db_path or getattr(cfg, "DB_PATH", "") or getattr(cfg, "TRADE_DB_PATH", "")
    if not raw_path:
        _record_startup_boundary("DB_READY_FAILED", error="DB_PATH is empty")
        raise RuntimeError("DB_PATH is empty. Set DB_PATH to a writable sqlite file path.")
    path = normalize_db_path(raw_path)
    cfg.DB_PATH = str(path)
    cfg.TRADE_DB_PATH = str(path)
    _ensure_permissions(path)

    payload: Dict[str, Any] = {
        "ts_epoch": now_utc_epoch(),
        "ts_ist": now_ist().isoformat(),
        "db_path": str(path),
        "ok": False,
    }
    try:
        probe_db_write(path)
        payload["ok"] = True
        _log_event({**payload, "event": "DB_PROBE_OK"})
    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}:{exc}"
        _log_event({**payload, "event": "DB_PROBE_FAIL"})
        _record_startup_boundary("DB_READY_FAILED", details={"db_path": str(path)}, error=payload["error"])
        raise RuntimeError(
            "DB probe failed (create/insert/delete): "
            f"{payload['error']} path={path}"
        ) from exc

    # Clear db_write_fail halt if we recovered.
    try:
        state = risk_halt.load_halt()
        if state.get("halted") and state.get("reason") == "db_write_fail":
            risk_halt.clear_halt()
            _log_event({**payload, "event": "DB_HALT_CLEARED"})
    except Exception:
        pass

    _record_startup_boundary("DB_READY_COMPLETED", details={"db_path": str(path)})
    return payload

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from config import config as cfg


def _conn():
    Path(cfg.TRADE_DB_PATH).parent.mkdir(exist_ok=True)
    return sqlite3.connect(cfg.TRADE_DB_PATH)


def init_db():
    with _conn() as conn:
        conn.execute(
            """
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT,
            entity_id TEXT,
            proposed_state TEXT,
            report_path TEXT,
            status TEXT,
            requested_by TEXT,
            reviewer_id TEXT,
            reason TEXT,
            created_epoch REAL,
            created_iso TEXT,
            decided_epoch REAL,
            decided_iso TEXT
        )
        """
        )
        # backward-compatible column adds
        for col in (
            "report_path",
            "status",
            "requested_by",
            "reviewer_id",
            "reason",
            "created_epoch",
            "created_iso",
            "decided_epoch",
            "decided_iso",
        ):
            try:
                conn.execute(f"ALTER TABLE approvals ADD COLUMN {col} TEXT")
            except Exception:
                pass


def propose(entity_type: str, entity_id: str, proposed_state: str, report_path: str, requested_by: str | None = None, reason: str | None = None):
    init_db()
    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    with _conn() as conn:
        cur = conn.execute(
            """
        INSERT INTO approvals
        (entity_type, entity_id, proposed_state, report_path, status, requested_by, reason, created_epoch, created_iso)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
            (
                entity_type,
                entity_id,
                proposed_state,
                report_path,
                "PENDING",
                requested_by,
                reason,
                now_epoch,
                now_iso,
            ),
        )
        return cur.lastrowid


def list_pending(entity_type: str | None = None):
    init_db()
    with _conn() as conn:
        if entity_type:
            cur = conn.execute(
                "SELECT * FROM approvals WHERE status='PENDING' AND entity_type=? ORDER BY created_epoch ASC",
                (entity_type,),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM approvals WHERE status='PENDING' ORDER BY created_epoch ASC"
            )
        return cur.fetchall()


def approve(request_id: int, reviewer_id: str, reason: str | None = None):
    init_db()
    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    with _conn() as conn:
        conn.execute(
            """
        UPDATE approvals
        SET status='APPROVED', reviewer_id=?, reason=?, decided_epoch=?, decided_iso=?
        WHERE id=?
        """,
            (reviewer_id, reason, now_epoch, now_iso, request_id),
        )


def reject(request_id: int, reviewer_id: str, reason: str | None = None):
    init_db()
    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    with _conn() as conn:
        conn.execute(
            """
        UPDATE approvals
        SET status='REJECTED', reviewer_id=?, reason=?, decided_epoch=?, decided_iso=?
        WHERE id=?
        """,
            (reviewer_id, reason, now_epoch, now_iso, request_id),
        )


def is_approved(entity_type: str, entity_id: str, proposed_state: str) -> bool:
    init_db()
    with _conn() as conn:
        cur = conn.execute(
            """
        SELECT status
        FROM approvals
        WHERE entity_type=? AND entity_id=? AND proposed_state=?
        ORDER BY created_epoch DESC
        LIMIT 1
        """,
            (entity_type, entity_id, proposed_state),
        )
        row = cur.fetchone()
    if not row:
        return False
    return row[0] == "APPROVED"

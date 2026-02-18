import sqlite3
import time
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from config import config as cfg
from core.audit_log import append_event


ORDER_APPROVAL_STATUS = {
    "PENDING",
    "APPROVED",
    "REJECTED",
    "EXPIRED",
    "USED",
}


def _conn(timeout: float = 5.0, isolation_level: Optional[str] = "DEFERRED"):
    Path(cfg.TRADE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(cfg.TRADE_DB_PATH, timeout=timeout, isolation_level=isolation_level)


def _utc_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _ttl(ttl_sec: Optional[int]) -> int:
    if ttl_sec is not None:
        return int(ttl_sec)
    return int(getattr(cfg, "ORDER_APPROVAL_TTL_SEC", getattr(cfg, "APPROVAL_TTL_SEC", 600)))


def _arm_ttl(arm_ttl_sec: Optional[int]) -> int:
    if arm_ttl_sec is not None:
        return int(arm_ttl_sec)
    return int(getattr(cfg, "ORDER_ARM_TTL_SEC", os.getenv("ORDER_ARM_TTL_SEC", "60")))


def _normalize_status(status: str) -> str:
    value = str(status or "").upper().strip()
    if value not in ORDER_APPROVAL_STATUS:
        raise ValueError(f"invalid_order_approval_status:{value}")
    return value


def _audit_transition(
    order_intent_hash: str,
    event: str,
    status: Optional[str],
    detail: Optional[str] = None,
    actor: Optional[str] = None,
) -> None:
    payload = {
        "event_type": "ORDER_APPROVAL",
        "event": event,
        "order_intent_hash": order_intent_hash,
        "status": status,
        "detail": detail,
        "actor": actor,
    }
    try:
        append_event(payload)
    except Exception as exc:
        print(f"[ORDER_APPROVAL_AUDIT_ERROR] {exc} | payload={payload}")


def init_db():
    with _conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
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

        conn.execute(
            """
        CREATE TABLE IF NOT EXISTS order_approvals (
            order_intent_hash TEXT PRIMARY KEY,
            created_at_epoch REAL NOT NULL,
            created_at_iso TEXT,
            expires_at_epoch REAL NOT NULL,
            expires_at_iso TEXT,
            approver_id TEXT,
            channel TEXT,
            status TEXT NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED','EXPIRED','USED')),
            reject_reason TEXT,
            reason TEXT,
            review_packet_snapshot TEXT,
            approved_at_epoch REAL,
            approved_at_iso TEXT,
            used_at_epoch REAL,
            used_at_iso TEXT,
            used_by TEXT,
            armed_at_epoch REAL,
            armed_at_iso TEXT,
            armed_expires_at_epoch REAL,
            armed_expires_at_iso TEXT,
            armed_by TEXT,
            armed_channel TEXT,
            updated_at_epoch REAL,
            updated_at_iso TEXT
        )
        """
        )
        for col_def in (
            "created_at_iso TEXT",
            "expires_at_iso TEXT",
            "reject_reason TEXT",
            "reason TEXT",
            "review_packet_snapshot TEXT",
            "approved_at_epoch REAL",
            "approved_at_iso TEXT",
            "used_at_iso TEXT",
            "updated_at_iso TEXT",
            "armed_at_epoch REAL",
            "armed_at_iso TEXT",
            "armed_expires_at_epoch REAL",
            "armed_expires_at_iso TEXT",
            "armed_by TEXT",
            "armed_channel TEXT",
        ):
            col = col_def.split()[0]
            try:
                conn.execute(f"ALTER TABLE order_approvals ADD COLUMN {col_def}")
            except Exception:
                pass
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_order_approvals_status_expiry ON order_approvals(status, expires_at_epoch)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_order_approvals_armed_expiry ON order_approvals(armed_expires_at_epoch)"
        )


def propose(entity_type: str, entity_id: str, proposed_state: str, report_path: str, requested_by: Optional[str] = None, reason: Optional[str] = None):
    init_db()
    now_epoch = time.time()
    now_iso = _utc_iso(now_epoch)
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


def list_pending(entity_type: Optional[str] = None):
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


def approve(request_id: int, reviewer_id: str, reason: Optional[str] = None):
    """
    Backward-compatible approve:
    - old path: approve(request_id:int, reviewer_id:str, reason)
    - order-intent path: approve(intent_hash:str, approver_id:str)
    """
    if isinstance(request_id, str):
        ok, status = approve_intent(request_id, reviewer_id)
        if not ok:
            raise ValueError(status)
        return
    init_db()
    now_epoch = time.time()
    now_iso = _utc_iso(now_epoch)
    with _conn() as conn:
        conn.execute(
            """
        UPDATE approvals
        SET status='APPROVED', reviewer_id=?, reason=?, decided_epoch=?, decided_iso=?
        WHERE id=?
        """,
            (reviewer_id, reason, now_epoch, now_iso, request_id),
        )


def reject(request_id: int, reviewer_id: str, reason: Optional[str] = None):
    """
    Backward-compatible reject:
    - old path: reject(request_id:int, reviewer_id:str, reason)
    - order-intent path: reject(intent_hash:str, approver_id:str, reason)
    """
    if isinstance(request_id, str):
        ok, status = reject_intent(request_id, reviewer_id, reason=reason)
        if not ok:
            raise ValueError(status)
        return
    init_db()
    now_epoch = time.time()
    now_iso = _utc_iso(now_epoch)
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


def create_proposal(
    intent_hash: str,
    approver_id: Optional[str],
    expires_at: float,
    channel: str = "cli",
    metadata: Optional[dict] = None,
) -> Tuple[bool, str]:
    """
    Create a PENDING approval proposal bound to an exact order intent hash.
    """
    init_db()
    if not intent_hash:
        return False, "approval_hash_missing"
    now_epoch = float(time.time())
    now_iso = _utc_iso(now_epoch)
    try:
        expires_epoch = float(expires_at)
    except Exception:
        return False, "approval_expiry_invalid"
    expires_iso = _utc_iso(expires_epoch)
    reason = None
    review_packet_snapshot = None
    if isinstance(metadata, dict):
        reason = metadata.get("reason")
        snapshot = metadata.get("review_packet_snapshot")
        if snapshot is not None:
            try:
                review_packet_snapshot = snapshot if isinstance(snapshot, str) else json.dumps(snapshot, sort_keys=True)
            except Exception:
                review_packet_snapshot = None
    return create_order_approval(
        order_intent_hash=intent_hash,
        approver_id=approver_id,
        channel=channel,
        ttl_sec=max(int(expires_epoch - now_epoch), 0),
        status="PENDING",
        now_epoch=now_epoch,
        reject_reason=reason,
        review_packet_snapshot=review_packet_snapshot,
        reason=reason,
        expires_at_epoch=expires_epoch,
        created_at_iso=now_iso,
        expires_at_iso=expires_iso,
    )


def approve_intent(intent_hash: str, approver_id: Optional[str]) -> Tuple[bool, str]:
    """
    Set intent status to APPROVED when not expired and not consumed.
    """
    init_db()
    if not intent_hash:
        return False, "approval_hash_missing"
    now_epoch = float(time.time())
    now_iso = _utc_iso(now_epoch)
    with _conn(timeout=1.0, isolation_level=None) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status, expires_at_epoch FROM order_approvals WHERE order_intent_hash=?",
            (intent_hash,),
        ).fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return False, "approval_missing"
        status, expires_at_epoch = row
        status = str(status or "").upper()
        if status == "USED":
            conn.execute("ROLLBACK")
            return False, "approval_used"
        if status == "REJECTED":
            conn.execute("ROLLBACK")
            return False, "approval_rejected"
        if status == "EXPIRED":
            conn.execute("ROLLBACK")
            return False, "approval_expired"
        try:
            expires = float(expires_at_epoch)
        except Exception:
            conn.execute("ROLLBACK")
            return False, "approval_expiry_invalid"
        if now_epoch > expires:
            conn.execute(
                """
                UPDATE order_approvals
                SET status='EXPIRED', updated_at_epoch=?, updated_at_iso=?
                WHERE order_intent_hash=?
                """,
                (now_epoch, now_iso, intent_hash),
            )
            conn.execute("COMMIT")
            _audit_transition(intent_hash, "SET_STATUS", "EXPIRED", "expired_before_approve", approver_id)
            return False, "approval_expired"
        conn.execute(
            """
            UPDATE order_approvals
            SET status='APPROVED', approver_id=?, approved_at_epoch=?, approved_at_iso=?, updated_at_epoch=?, updated_at_iso=?
            WHERE order_intent_hash=? AND status IN ('PENDING','APPROVED')
            """,
            (approver_id, now_epoch, now_iso, now_epoch, now_iso, intent_hash),
        )
        conn.execute("COMMIT")
    _audit_transition(intent_hash, "SET_STATUS", "APPROVED", "approved", approver_id)
    return True, "approved"


def reject_intent(intent_hash: str, approver_id: Optional[str], reason: Optional[str] = None) -> Tuple[bool, str]:
    init_db()
    if not intent_hash:
        return False, "approval_hash_missing"
    now_epoch = float(time.time())
    now_iso = _utc_iso(now_epoch)
    with _conn(timeout=1.0, isolation_level=None) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status FROM order_approvals WHERE order_intent_hash=?",
            (intent_hash,),
        ).fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return False, "approval_missing"
        status = str(row[0] or "").upper()
        if status == "USED":
            conn.execute("ROLLBACK")
            return False, "approval_used"
        conn.execute(
            """
            UPDATE order_approvals
            SET status='REJECTED', approver_id=?, reject_reason=?, reason=?, updated_at_epoch=?, updated_at_iso=?
            WHERE order_intent_hash=?
            """,
            (approver_id, reason, reason, now_epoch, now_iso, intent_hash),
        )
        conn.execute("COMMIT")
    _audit_transition(intent_hash, "SET_STATUS", "REJECTED", reason, approver_id)
    return True, "rejected"


def create_order_approval(
    order_intent_hash: str,
    approver_id: Optional[str],
    channel: str = "cli",
    ttl_sec: Optional[int] = None,
    status: str = "PENDING",
    now_epoch: Optional[float] = None,
    reject_reason: Optional[str] = None,
    review_packet_snapshot: Optional[str] = None,
    reason: Optional[str] = None,
    expires_at_epoch: Optional[float] = None,
    created_at_iso: Optional[str] = None,
    expires_at_iso: Optional[str] = None,
) -> Tuple[bool, str]:
    init_db()
    if not order_intent_hash:
        return False, "approval_hash_missing"
    try:
        status = _normalize_status(status)
    except Exception as exc:
        return False, str(exc)
    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    if expires_at_epoch is None:
        ttl = _ttl(ttl_sec)
        expires_at = now_epoch + max(ttl, 0)
    else:
        expires_at = float(expires_at_epoch)
    now_iso = created_at_iso or _utc_iso(now_epoch)
    expires_iso = expires_at_iso or _utc_iso(expires_at)
    approved_at_epoch = now_epoch if status == "APPROVED" else None
    approved_at_iso = now_iso if status == "APPROVED" else None
    with _conn() as conn:
        row = conn.execute(
            "SELECT status FROM order_approvals WHERE order_intent_hash=?",
            (order_intent_hash,),
        ).fetchone()
        if row and str(row[0] or "").upper() == "USED":
            return False, "approval_already_used"
        conn.execute(
            """
                INSERT INTO order_approvals
                (
                    order_intent_hash, created_at_epoch, created_at_iso,
                    expires_at_epoch, expires_at_iso, approver_id, channel,
                    status, reject_reason, reason, review_packet_snapshot, approved_at_epoch, approved_at_iso,
                    used_at_epoch, used_at_iso, used_by,
                    armed_at_epoch, armed_at_iso, armed_expires_at_epoch, armed_expires_at_iso, armed_by, armed_channel,
                    updated_at_epoch, updated_at_iso
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,?,?)
                ON CONFLICT(order_intent_hash) DO UPDATE SET
                    created_at_epoch=excluded.created_at_epoch,
                    created_at_iso=excluded.created_at_iso,
                    expires_at_epoch=excluded.expires_at_epoch,
                    expires_at_iso=excluded.expires_at_iso,
                    approver_id=excluded.approver_id,
                    channel=excluded.channel,
                    status=excluded.status,
                    reject_reason=excluded.reject_reason,
                    reason=excluded.reason,
                    review_packet_snapshot=excluded.review_packet_snapshot,
                    approved_at_epoch=excluded.approved_at_epoch,
                    approved_at_iso=excluded.approved_at_iso,
                    used_at_epoch=NULL,
                    used_at_iso=NULL,
                    used_by=NULL,
                    armed_at_epoch=NULL,
                    armed_at_iso=NULL,
            armed_expires_at_epoch=NULL,
            armed_expires_at_iso=NULL,
            armed_by=NULL,
            armed_channel=NULL,
            updated_at_epoch=excluded.updated_at_epoch,
            updated_at_iso=excluded.updated_at_iso
        """,
            (
                order_intent_hash,
                now_epoch,
                now_iso,
                expires_at,
                expires_iso,
                approver_id,
                channel,
                status,
                reject_reason,
                reason,
                review_packet_snapshot,
                approved_at_epoch,
                approved_at_iso,
                now_epoch,
                now_iso,
            ),
        )
    _audit_transition(
        order_intent_hash=order_intent_hash,
        event="SET_STATUS",
        status=status,
        detail=f"channel={channel}",
        actor=approver_id,
    )
    return True, status.lower()


def approve_order_intent(
    order_intent_hash: str,
    approver_id: Optional[str],
    channel: str = "cli",
    ttl_sec: Optional[int] = None,
    now_epoch: Optional[float] = None,
) -> Tuple[bool, str]:
    return create_order_approval(
        order_intent_hash=order_intent_hash,
        approver_id=approver_id,
        channel=channel,
        ttl_sec=ttl_sec,
        status="APPROVED",
        now_epoch=now_epoch,
    )


def reject_order_intent(
    order_intent_hash: str,
    approver_id: Optional[str],
    channel: str = "cli",
    ttl_sec: Optional[int] = None,
    now_epoch: Optional[float] = None,
    reject_reason: Optional[str] = None,
) -> Tuple[bool, str]:
    return create_order_approval(
        order_intent_hash=order_intent_hash,
        approver_id=approver_id,
        channel=channel,
        ttl_sec=ttl_sec,
        status="REJECTED",
        now_epoch=now_epoch,
        reject_reason=reject_reason,
    )


def arm_order_intent(
    order_intent_hash: str,
    approver_id: Optional[str],
    channel: str = "cli",
    arm_ttl_sec: Optional[int] = None,
    now_epoch: Optional[float] = None,
    max_retries: int = 5,
) -> Tuple[bool, str]:
    init_db()
    if not order_intent_hash:
        return False, "approval_hash_missing"
    arm_ttl = _arm_ttl(arm_ttl_sec)
    if arm_ttl <= 0:
        return False, "approval_arm_ttl_invalid"
    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    now_iso = _utc_iso(now_epoch)

    for attempt in range(max_retries):
        conn = None
        try:
            conn = _conn(timeout=1.0, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT status, expires_at_epoch
                FROM order_approvals
                WHERE order_intent_hash=?
                """,
                (order_intent_hash,),
            ).fetchone()
            if not row:
                conn.execute("ROLLBACK")
                return False, "approval_missing"
            status, expires_at_epoch = row
            status = str(status or "").upper()
            if status == "USED":
                conn.execute("ROLLBACK")
                return False, "approval_used"
            if status == "PENDING":
                conn.execute("ROLLBACK")
                return False, "approval_pending"
            if status == "REJECTED":
                conn.execute("ROLLBACK")
                return False, "approval_rejected"
            if status == "EXPIRED":
                conn.execute("ROLLBACK")
                return False, "approval_expired"
            if status != "APPROVED":
                conn.execute("ROLLBACK")
                return False, "approval_not_approved"
            try:
                approval_expires = float(expires_at_epoch)
            except Exception:
                conn.execute("ROLLBACK")
                return False, "approval_expiry_invalid"
            if now_epoch > approval_expires:
                conn.execute(
                    """
                    UPDATE order_approvals
                    SET status='EXPIRED', updated_at_epoch=?, updated_at_iso=?
                    WHERE order_intent_hash=? AND status='APPROVED'
                    """,
                    (now_epoch, now_iso, order_intent_hash),
                )
                conn.execute("COMMIT")
                _audit_transition(
                    order_intent_hash=order_intent_hash,
                    event="SET_STATUS",
                    status="EXPIRED",
                    detail="expired_before_arm",
                    actor=approver_id,
                )
                return False, "approval_expired"

            armed_expires = min(now_epoch + arm_ttl, approval_expires)
            armed_expires_iso = _utc_iso(armed_expires)
            cur = conn.execute(
                """
                UPDATE order_approvals
                SET armed_at_epoch=?, armed_at_iso=?, armed_expires_at_epoch=?, armed_expires_at_iso=?,
                    armed_by=?, armed_channel=?, updated_at_epoch=?, updated_at_iso=?
                WHERE order_intent_hash=? AND status='APPROVED' AND expires_at_epoch>=?
                """,
                (
                    now_epoch,
                    now_iso,
                    armed_expires,
                    armed_expires_iso,
                    approver_id,
                    channel,
                    now_epoch,
                    now_iso,
                    order_intent_hash,
                    now_epoch,
                ),
            )
            if cur.rowcount != 1:
                conn.execute("ROLLBACK")
                return False, "approval_race_lost"
            conn.execute("COMMIT")
            _audit_transition(
                order_intent_hash=order_intent_hash,
                event="ARMED",
                status="APPROVED",
                detail=f"armed_until={armed_expires}",
                actor=approver_id,
            )
            return True, "approval_armed"
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "locked" in message or "busy" in message:
                time.sleep(0.05 * (attempt + 1))
                continue
            return False, f"approval_store_error:{exc}"
        except Exception as exc:
            return False, f"approval_store_error:{exc}"
        finally:
            if conn is not None:
                conn.close()
    return False, "approval_store_locked"


def consume_valid_approval(
    order_intent_hash: str,
    approver_id: Optional[str] = None,
    ttl_sec: Optional[int] = None,
    now: Optional[float] = None,
    now_epoch: Optional[float] = None,
    require_armed: bool = False,
    max_retries: int = 5,
) -> Tuple[bool, str]:
    init_db()
    if not order_intent_hash:
        return False, "approval_hash_missing"
    if now is not None and now_epoch is None:
        now_epoch = now
    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    ttl = _ttl(ttl_sec)
    if ttl <= 0:
        return False, "approval_ttl_invalid"

    for attempt in range(max_retries):
        conn = None
        try:
            conn = _conn(timeout=1.0, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT status, expires_at_epoch, armed_expires_at_epoch
                FROM order_approvals
                WHERE order_intent_hash=?
                """,
                (order_intent_hash,),
            ).fetchone()
            if not row:
                conn.execute("ROLLBACK")
                return False, "approval_missing"

            status, expires_at_epoch, armed_expires_at_epoch = row
            status = str(status or "").upper()
            if status == "USED":
                conn.execute("ROLLBACK")
                return False, "approval_used"
            if status == "PENDING":
                conn.execute("ROLLBACK")
                return False, "approval_pending"
            if status == "REJECTED":
                conn.execute("ROLLBACK")
                return False, "approval_rejected"
            if status == "EXPIRED":
                conn.execute("ROLLBACK")
                return False, "approval_expired"
            if status != "APPROVED":
                conn.execute("ROLLBACK")
                return False, "approval_not_approved"

            try:
                expires = float(expires_at_epoch)
            except Exception:
                conn.execute("ROLLBACK")
                return False, "approval_expiry_invalid"
            if now_epoch > expires:
                now_iso = _utc_iso(now_epoch)
                conn.execute(
                    """
                    UPDATE order_approvals
                    SET status='EXPIRED', updated_at_epoch=?, updated_at_iso=?
                    WHERE order_intent_hash=? AND status='APPROVED'
                    """,
                    (now_epoch, now_iso, order_intent_hash),
                )
                conn.execute("COMMIT")
                _audit_transition(
                    order_intent_hash=order_intent_hash,
                    event="SET_STATUS",
                    status="EXPIRED",
                    detail="expired_before_consume",
                    actor=approver_id,
                )
                return False, "approval_expired"

            if require_armed:
                if armed_expires_at_epoch is None:
                    conn.execute("ROLLBACK")
                    return False, "approval_not_armed"
                try:
                    armed_expires = float(armed_expires_at_epoch)
                except Exception:
                    conn.execute("ROLLBACK")
                    return False, "approval_arm_expiry_invalid"
                if now_epoch > armed_expires:
                    now_iso = _utc_iso(now_epoch)
                    conn.execute(
                        """
                        UPDATE order_approvals
                        SET armed_at_epoch=NULL, armed_at_iso=NULL, armed_expires_at_epoch=NULL, armed_expires_at_iso=NULL,
                            armed_by=NULL, armed_channel=NULL, updated_at_epoch=?, updated_at_iso=?
                        WHERE order_intent_hash=? AND status='APPROVED'
                        """,
                        (now_epoch, now_iso, order_intent_hash),
                    )
                    conn.execute("COMMIT")
                    _audit_transition(
                        order_intent_hash=order_intent_hash,
                        event="DISARMED",
                        status="APPROVED",
                        detail="arm_window_expired",
                        actor=approver_id,
                    )
                    return False, "approval_arm_expired"

            now_iso = _utc_iso(now_epoch)
            where_clause = "status='APPROVED' AND expires_at_epoch>=?"
            params = [now_epoch, now_iso, approver_id, now_epoch, now_iso, order_intent_hash, now_epoch]
            if require_armed:
                where_clause += " AND armed_expires_at_epoch>=?"
                params.append(now_epoch)
            cur = conn.execute(
                """
                UPDATE order_approvals
                SET status='USED', used_at_epoch=?, used_at_iso=?, used_by=?,
                    armed_at_epoch=NULL, armed_at_iso=NULL, armed_expires_at_epoch=NULL, armed_expires_at_iso=NULL,
                    armed_by=NULL, armed_channel=NULL, updated_at_epoch=?, updated_at_iso=?
                WHERE order_intent_hash=? AND """
                + where_clause,
                tuple(params),
            )
            if cur.rowcount != 1:
                conn.execute("ROLLBACK")
                return False, "approval_race_lost"
            conn.execute("COMMIT")
            _audit_transition(
                order_intent_hash=order_intent_hash,
                event="CONSUMED",
                status="USED",
                detail=f"require_armed={require_armed}",
                actor=approver_id,
            )
            return True, "approved_and_used"
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "locked" in message or "busy" in message:
                time.sleep(0.05 * (attempt + 1))
                continue
            return False, f"approval_store_error:{exc}"
        except Exception as exc:
            return False, f"approval_store_error:{exc}"
        finally:
            if conn is not None:
                conn.close()
    return False, "approval_store_locked"


def approve_and_consume_order_intent(
    order_intent_hash: str,
    approver_id: Optional[str],
    channel: str = "cli",
    ttl_sec: Optional[int] = None,
    now_epoch: Optional[float] = None,
    max_retries: int = 5,
) -> Tuple[bool, str]:
    init_db()
    if not order_intent_hash:
        return False, "approval_hash_missing"
    ttl = _ttl(ttl_sec)
    if ttl <= 0:
        return False, "approval_ttl_invalid"
    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    expires_at = now_epoch + ttl
    now_iso = _utc_iso(now_epoch)
    expires_iso = _utc_iso(expires_at)

    for attempt in range(max_retries):
        conn = None
        try:
            conn = _conn(timeout=1.0, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT status FROM order_approvals WHERE order_intent_hash=?",
                (order_intent_hash,),
            ).fetchone()
            if existing and str(existing[0] or "").upper() == "USED":
                conn.execute("ROLLBACK")
                return False, "approval_used"
            conn.execute(
                """
                INSERT INTO order_approvals
                (
                    order_intent_hash, created_at_epoch, created_at_iso,
                    expires_at_epoch, expires_at_iso, approver_id, channel,
                    status, reject_reason, used_at_epoch, used_at_iso, used_by,
                    armed_at_epoch, armed_at_iso, armed_expires_at_epoch, armed_expires_at_iso, armed_by, armed_channel,
                    updated_at_epoch, updated_at_iso
                )
                VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,?,?)
                ON CONFLICT(order_intent_hash) DO UPDATE SET
                    created_at_epoch=excluded.created_at_epoch,
                    created_at_iso=excluded.created_at_iso,
                    expires_at_epoch=excluded.expires_at_epoch,
                    expires_at_iso=excluded.expires_at_iso,
                    approver_id=excluded.approver_id,
                    channel=excluded.channel,
                    status='APPROVED',
                    reject_reason=NULL,
                    used_at_epoch=NULL,
                    used_at_iso=NULL,
                    used_by=NULL,
                    armed_at_epoch=NULL,
                    armed_at_iso=NULL,
                    armed_expires_at_epoch=NULL,
                    armed_expires_at_iso=NULL,
                    armed_by=NULL,
                    armed_channel=NULL,
                    updated_at_epoch=excluded.updated_at_epoch,
                    updated_at_iso=excluded.updated_at_iso
                """,
                (
                    order_intent_hash,
                    now_epoch,
                    now_iso,
                    expires_at,
                    expires_iso,
                    approver_id,
                    channel,
                    "APPROVED",
                    None,
                    now_epoch,
                    now_iso,
                ),
            )
            cur = conn.execute(
                """
                UPDATE order_approvals
                SET status='USED', used_at_epoch=?, used_at_iso=?, used_by=?,
                    armed_at_epoch=NULL, armed_at_iso=NULL, armed_expires_at_epoch=NULL, armed_expires_at_iso=NULL,
                    armed_by=NULL, armed_channel=NULL, updated_at_epoch=?, updated_at_iso=?
                WHERE order_intent_hash=? AND status='APPROVED' AND expires_at_epoch>=?
                """,
                (now_epoch, now_iso, approver_id, now_epoch, now_iso, order_intent_hash, now_epoch),
            )
            if cur.rowcount != 1:
                conn.execute("ROLLBACK")
                return False, "approval_race_lost"
            conn.execute("COMMIT")
            _audit_transition(
                order_intent_hash=order_intent_hash,
                event="APPROVED_AND_CONSUMED",
                status="USED",
                detail=f"channel={channel}",
                actor=approver_id,
            )
            return True, "approved_and_used"
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "locked" in message or "busy" in message:
                time.sleep(0.05 * (attempt + 1))
                continue
            return False, f"approval_store_error:{exc}"
        except Exception as exc:
            return False, f"approval_store_error:{exc}"
        finally:
            if conn is not None:
                conn.close()
    return False, "approval_store_locked"

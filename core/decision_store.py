"""SQLite persistence for Decision objects."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from core.decision import Decision


class DecisionStore:
    def __init__(self, db_path: str, retries: int = 3, retry_sleep_sec: float = 0.1):
        self.db_path = db_path
        self.retries = retries
        self.retry_sleep_sec = retry_sleep_sec
        self.init(db_path)

    def init(self, db_path: Optional[str] = None) -> None:
        if db_path is not None:
            self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS decision_log (
                    decision_id TEXT PRIMARY KEY,
                    ts_epoch INTEGER,
                    run_id TEXT,
                    symbol TEXT,
                    status TEXT,
                    decision_json TEXT
                )
                """
            )
            conn.commit()

    def _with_retry(self, fn):
        last_err = None
        for _ in range(self.retries):
            try:
                return fn()
            except sqlite3.OperationalError as err:
                msg = str(err).lower()
                if "locked" in msg or "busy" in msg:
                    last_err = err
                    time.sleep(self.retry_sleep_sec)
                    continue
                raise
        return None

    def save_decision(self, decision: Decision) -> bool:
        payload = decision.to_dict()
        def _op():
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO decision_log
                    (decision_id, ts_epoch, run_id, symbol, status, decision_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        decision.decision_id,
                        int(decision.meta.ts_epoch),
                        decision.meta.run_id,
                        decision.meta.symbol,
                        decision.outcome.status.value,
                        json.dumps(payload, separators=(",", ":"), sort_keys=True),
                    ),
                )
                conn.commit()
                return True
        return bool(self._with_retry(_op))

    def update_status(self, decision_id: str, status: str, reject_reasons: Optional[List[str]] = None) -> bool:
        def _op():
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(
                    "SELECT decision_json FROM decision_log WHERE decision_id=?",
                    (decision_id,),
                )
                row = cur.fetchone()
                if not row:
                    return False
                payload = json.loads(row[0])
                payload.setdefault("outcome", {})
                payload["outcome"]["status"] = status
                if reject_reasons is not None:
                    payload["outcome"]["reject_reasons"] = list(reject_reasons)
                conn.execute(
                    "UPDATE decision_log SET status=?, decision_json=? WHERE decision_id=?",
                    (status, json.dumps(payload, separators=(",", ":"), sort_keys=True), decision_id),
                )
                conn.commit()
                return True
        return bool(self._with_retry(_op))

    def list_recent(self, limit: int = 50, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        def _op():
            with sqlite3.connect(self.db_path) as conn:
                if symbol:
                    cur = conn.execute(
                        """
                        SELECT decision_json FROM decision_log
                        WHERE symbol=? ORDER BY ts_epoch DESC LIMIT ?
                        """,
                        (symbol, limit),
                    )
                else:
                    cur = conn.execute(
                        "SELECT decision_json FROM decision_log ORDER BY ts_epoch DESC LIMIT ?",
                        (limit,),
                    )
                rows = cur.fetchall()
                return [json.loads(r[0]) for r in rows]
        result = self._with_retry(_op)
        return result or []

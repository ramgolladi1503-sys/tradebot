from __future__ import annotations

import sqlite3
from pathlib import Path

from agentic_research.contracts import HypothesisRecord


class HypothesisRegistry:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hypotheses (
                    fingerprint TEXT PRIMARY KEY,
                    hypothesis_id TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    dataset_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def register(self, record: HypothesisRecord) -> tuple[bool, HypothesisRecord]:
        fingerprint = record.fingerprint()
        with self._connect() as conn:
            existing = conn.execute("SELECT payload_json FROM hypotheses WHERE fingerprint=?", (fingerprint,)).fetchone()
            if existing:
                return False, HypothesisRecord.model_validate_json(existing[0])
            conn.execute(
                "INSERT INTO hypotheses(fingerprint, hypothesis_id, strategy_id, dataset_hash, status, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (fingerprint, record.hypothesis_id, record.strategy_id, record.dataset_hash, record.status, record.model_dump_json()),
            )
        return True, record

    def list_for_strategy(self, strategy_id: str) -> list[HypothesisRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload_json FROM hypotheses WHERE strategy_id=? ORDER BY hypothesis_id", (strategy_id,)).fetchall()
        return [HypothesisRecord.model_validate_json(row[0]) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

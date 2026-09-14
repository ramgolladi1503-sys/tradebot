"""Durable, partitioned, and chain-verifiable storage for Trade Truth records."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Generator, Mapping

from core.log_writer import get_jsonl_writer
from core.paths import runtime_dir
from core.trade_truth.decision_hash import compute_record_integrity_hash
from core.trade_truth.models import TradeTruthRecord, TRUTH_SCHEMA_VERSION

logger = logging.getLogger(__name__)

DEFAULT_TRUTH_SUBDIR = "truth"


def default_partitioned_truth_path(session_date: str | None = None, session_id: str | None = None) -> Path:
    date_str = session_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sess_str = session_id or "default_session"
    return runtime_dir() / DEFAULT_TRUTH_SUBDIR / date_str / f"{sess_str}.jsonl"


class TruthStoreError(Exception):
    pass


class TruthStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path).expanduser() if path else default_partitioned_truth_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_record_hash = "GENESIS"
        self._next_sequence_number = 1
        self._sync_chain_head()
        # Bounded thread-safe writer with permanent archival retention
        self._writer = get_jsonl_writer(
            self.path,
            max_record_bytes=512 * 1024,
            max_file_bytes=100 * 1024 * 1024,
            backup_count=50,
        )

    def _sync_chain_head(self) -> None:
        """Read end of current store to sync sequence number and previous hash."""
        if not self.path.exists():
            return
        last_hash = "GENESIS"
        last_seq = 0
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    rec = json.loads(raw)
                    last_hash = str(rec.get("record_hash") or "GENESIS")
                    last_seq = int(rec.get("sequence_number") or last_seq + 1)
            self._last_record_hash = last_hash
            self._next_sequence_number = last_seq + 1
        except Exception as exc:
            logger.warning("Could not sync chain head in %s: %s", self.path, exc)

    @property
    def last_record_hash(self) -> str:
        return self._last_record_hash

    @property
    def next_sequence_number(self) -> int:
        return self._next_sequence_number

    def write_record(self, record: TradeTruthRecord) -> bool:
        """Write a TradeTruthRecord append-only to durable store.

        Verifies schema version, immutability flags, and integrity hash before persisting.
        """
        payload = record.to_dict()

        if record.schema_version != TRUTH_SCHEMA_VERSION:
            raise TruthStoreError(f"Schema mismatch: expected {TRUTH_SCHEMA_VERSION}, got {record.schema_version}")

        if record.is_order_action or record.broker_api_called or record.orders_placed > 0:
            raise TruthStoreError("Safety invariant violated: write contains forbidden order action or broker call")

        expected_hash = compute_record_integrity_hash(payload)
        if record.record_hash != expected_hash:
            raise TruthStoreError(f"Integrity hash mismatch: record contains {record.record_hash}, calculated {expected_hash}")

        success = self._writer.write(payload)
        if not success:
            logger.error("Failed to append truth record to %s (writer dropped payload)", self.path)
            raise TruthStoreError(f"PERSISTENCE_FAILURE: failed to append truth record to {self.path}")

        self._last_record_hash = record.record_hash
        self._next_sequence_number = record.sequence_number + 1
        return True

    def read_records(self) -> Generator[dict[str, Any], None, None]:
        """Generator reading all records in store."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    yield data
                except Exception as exc:
                    logger.error("Corrupt JSON on line %d in %s: %s", line_no, self.path, exc)
                    raise TruthStoreError(f"TRUTH_CORRUPT: line {line_no} invalid JSON in {self.path}") from exc

    def get_by_trace_id(self, trace_id: str) -> list[dict[str, Any]]:
        """Look up all truth records matching a trace_id."""
        matches = []
        for rec in self.read_records():
            identity = rec.get("identity") or {}
            if identity.get("trace_id") == trace_id or identity.get("parent_trace_id") == trace_id:
                matches.append(rec)
        return matches

    def verify_chain_integrity(self) -> tuple[bool, str]:
        """Verify sequential cryptographic chain integrity across all records in file."""
        if not self.path.exists():
            return True, "EMPTY"

        expected_prev_hash = "GENESIS"
        expected_seq = 1

        for rec in self.read_records():
            seq = rec.get("sequence_number", 1)
            prev_hash = rec.get("previous_record_hash", "GENESIS")
            rec_hash = rec.get("record_hash")

            if seq != expected_seq:
                return False, f"TRUTH_CHAIN_BROKEN: expected sequence {expected_seq}, got {seq}"
            if prev_hash != expected_prev_hash:
                return False, f"TRUTH_CHAIN_BROKEN: expected prev_hash {expected_prev_hash}, got {prev_hash}"

            calculated = compute_record_integrity_hash(rec)
            if rec_hash != calculated:
                return False, f"TRUTH_CORRUPT: record hash tampered at seq {seq}"

            expected_prev_hash = rec_hash
            expected_seq = seq + 1

        return True, "VALID_CHAIN"

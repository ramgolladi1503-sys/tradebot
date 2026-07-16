from __future__ import annotations

import contextlib
import json
import os
import re
import sqlite3
import tempfile
import threading
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Any, Iterator

from config import config as cfg
from core.fs_utils import ensure_parent_dir
from core.paths import trade_db_path


LINEAGE_STATES = frozenset({"EMITTED", "INVALIDATED", "EXPIRED"})
OUTBOX_STATES = frozenset({"PENDING", "LEASED", "PUBLISHED", "RETRYABLE_FAILED", "FAILED_FINAL"})
VALID_DIRECTIONS = frozenset({"BUY_CALL", "BUY_PUT"})
VALID_BOUNDARY_TYPES = frozenset({"ORB_HIGH", "ORB_LOW"})
IMMUTABLE_LINEAGE_FIELDS = (
    "strategy_id",
    "contract_version",
    "schema_version",
    "source_component",
    "symbol",
    "session_date",
    "direction",
    "boundary_type",
    "normalized_boundary_value",
    "breakout_timestamp_iso",
    "history_hash",
    "candidate_fingerprint",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso8601(value: str, *, field_name: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"missing_required_field:{field_name}")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception as exc:
        raise ValueError(f"invalid_iso8601:{field_name}") from exc
    return parsed


def _utc_from_iso(value: str, *, field_name: str) -> datetime:
    parsed = _parse_iso8601(value, field_name=field_name)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_session_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("missing_required_field:session_date")
    try:
        parsed = date.fromisoformat(text)
    except Exception as exc:
        raise ValueError("invalid_session_date") from exc
    normalized = parsed.isoformat()
    if normalized != text:
        raise ValueError("session_date_not_canonical")
    return normalized


def _validate_direction(value: str) -> str:
    text = str(value or "").strip().upper()
    if text not in VALID_DIRECTIONS:
        raise ValueError(f"invalid_direction:{text}")
    return text


def _validate_boundary_type(value: str) -> str:
    text = str(value or "").strip().upper()
    if text not in VALID_BOUNDARY_TYPES:
        raise ValueError(f"invalid_boundary_type:{text}")
    return text


def _validate_history_hash(value: str) -> str:
    text = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError("invalid_history_hash")
    return text


def _validate_non_empty(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"missing_required_field:{field_name}")
    return text


def _validate_json(value: str, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"missing_required_field:{field_name}")
    try:
        parsed = json.loads(text)
    except Exception as exc:
        raise ValueError(f"invalid_json:{field_name}") from exc
    normalized = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    if text != normalized:
        raise ValueError(f"non_canonical_json:{field_name}")
    return normalized


def _validate_schema_version(value: Any) -> int:
    try:
        out = int(value)
    except Exception as exc:
        raise ValueError("invalid_schema_version") from exc
    if out < 0:
        raise ValueError("invalid_schema_version")
    return out


def _validate_boundary_value(value: Any) -> float:
    try:
        out = float(value)
    except Exception as exc:
        raise ValueError("invalid_boundary_value") from exc
    if not (out == out) or out in (float("inf"), float("-inf")):
        raise ValueError("invalid_boundary_value")
    return out


def _validate_lease_seconds(value: Any | None) -> int:
    raw = 30 if value is None else value
    try:
        seconds = int(raw)
    except Exception as exc:
        raise ValueError("invalid_publication_lease_seconds") from exc
    if seconds < 5 or seconds > 300:
        raise ValueError("invalid_publication_lease_seconds")
    return seconds


def _classify_sqlite_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "locked" in message or "busy" in message:
        return "OWNER_BUSY"
    if (
        "unable to open database file" in message
        or "no such file" in message
        or "readonly" in message
        or "io error" in message
        or "disk i/o error" in message
    ):
        return "OWNER_UNAVAILABLE"
    if "schema" in message or "no such table" in message or "no such column" in message:
        return "OWNER_STATE_CONFLICT"
    return "ERROR"


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


@dataclass(frozen=True)
class OpeningRangeRetestProposal:
    setup_id: str
    strategy_id: str
    contract_version: str
    schema_version: int
    source_component: str
    symbol: str
    session_date: str
    direction: str
    boundary_type: str
    normalized_boundary_value: float
    breakout_timestamp_iso: str
    history_hash: str
    candidate_fingerprint: str
    candidate_payload_json: str
    created_at_iso: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "setup_id", _validate_non_empty(self.setup_id, "setup_id"))
        object.__setattr__(self, "strategy_id", _validate_non_empty(self.strategy_id, "strategy_id"))
        object.__setattr__(self, "contract_version", _validate_non_empty(self.contract_version, "contract_version"))
        object.__setattr__(self, "schema_version", _validate_schema_version(self.schema_version))
        object.__setattr__(self, "source_component", _validate_non_empty(self.source_component, "source_component"))
        object.__setattr__(self, "symbol", _validate_non_empty(self.symbol, "symbol"))
        object.__setattr__(self, "session_date", _validate_session_date(self.session_date))
        object.__setattr__(self, "direction", _validate_direction(self.direction))
        object.__setattr__(self, "boundary_type", _validate_boundary_type(self.boundary_type))
        object.__setattr__(self, "normalized_boundary_value", _validate_boundary_value(self.normalized_boundary_value))
        _parse_iso8601(self.breakout_timestamp_iso, field_name="breakout_timestamp_iso")
        object.__setattr__(self, "breakout_timestamp_iso", str(self.breakout_timestamp_iso).strip())
        object.__setattr__(self, "history_hash", _validate_history_hash(self.history_hash))
        object.__setattr__(self, "candidate_fingerprint", _validate_non_empty(self.candidate_fingerprint, "candidate_fingerprint"))
        object.__setattr__(self, "candidate_payload_json", _validate_json(self.candidate_payload_json, field_name="candidate_payload_json"))
        _parse_iso8601(self.created_at_iso, field_name="created_at_iso")
        object.__setattr__(self, "created_at_iso", str(self.created_at_iso).strip())

    def immutable_items(self) -> tuple[tuple[str, Any], ...]:
        return tuple((key, getattr(self, key)) for key in IMMUTABLE_LINEAGE_FIELDS)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LineageRecord:
    setup_id: str
    strategy_id: str
    contract_version: str
    schema_version: int
    source_component: str
    symbol: str
    session_date: str
    direction: str
    boundary_type: str
    normalized_boundary_value: float
    breakout_timestamp_iso: str
    history_hash: str
    candidate_fingerprint: str
    state: str
    created_at_iso: str
    emitted_at_iso: str | None
    invalidated_at_iso: str | None
    expired_at_iso: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "LineageRecord":
        data = dict(row)
        return cls(
            setup_id=str(data["setup_id"]),
            strategy_id=str(data["strategy_id"]),
            contract_version=str(data["contract_version"]),
            schema_version=int(data["schema_version"]),
            source_component=str(data["source_component"]),
            symbol=str(data["symbol"]),
            session_date=str(data["session_date"]),
            direction=str(data["direction"]),
            boundary_type=str(data["boundary_type"]),
            normalized_boundary_value=float(data["normalized_boundary_value"]),
            breakout_timestamp_iso=str(data["breakout_timestamp_iso"]),
            history_hash=str(data["history_hash"]),
            candidate_fingerprint=str(data["candidate_fingerprint"]),
            state=str(data["state"]),
            created_at_iso=str(data["created_at_iso"]),
            emitted_at_iso=data["emitted_at_iso"],
            invalidated_at_iso=data["invalidated_at_iso"],
            expired_at_iso=data["expired_at_iso"],
        )


@dataclass(frozen=True)
class OutboxRecord:
    outbox_id: str
    setup_id: str
    candidate_payload_json: str
    candidate_fingerprint: str
    publication_state: str
    publication_attempts: int
    created_at_iso: str
    next_attempt_at_iso: str | None
    published_at_iso: str | None
    last_attempt_at_iso: str | None
    last_error: str | None
    lease_token: str | None
    lease_owner_id: str | None
    lease_acquired_at_iso: str | None
    lease_expires_at_iso: str | None
    schema_version: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "OutboxRecord":
        data = dict(row)
        return cls(
            outbox_id=str(data["outbox_id"]),
            setup_id=str(data["setup_id"]),
            candidate_payload_json=str(data["candidate_payload_json"]),
            candidate_fingerprint=str(data["candidate_fingerprint"]),
            publication_state=str(data["publication_state"]),
            publication_attempts=int(data["publication_attempts"]),
            created_at_iso=str(data["created_at_iso"]),
            next_attempt_at_iso=data["next_attempt_at_iso"],
            published_at_iso=data["published_at_iso"],
            last_attempt_at_iso=data["last_attempt_at_iso"],
            last_error=data["last_error"],
            lease_token=data["lease_token"],
            lease_owner_id=data["lease_owner_id"],
            lease_acquired_at_iso=data["lease_acquired_at_iso"],
            lease_expires_at_iso=data["lease_expires_at_iso"],
            schema_version=int(data["schema_version"]),
        )


@dataclass(frozen=True)
class PublicationResult:
    result: str
    setup_id: str
    lineage_state: str | None = None
    publication_state: str | None = None
    publication_attempts: int | None = None
    outbox_id: str | None = None
    stale_lease_reclaimed: bool = False
    detail: str | None = None


@dataclass(frozen=True)
class LeaseResult:
    result: str
    setup_id: str
    publication_state: str | None = None
    publication_attempts: int | None = None
    lease_token: str | None = None
    lease_owner_id: str | None = None
    lease_acquired_at_iso: str | None = None
    lease_expires_at_iso: str | None = None
    stale_lease_reclaimed: bool = False
    detail: str | None = None


@dataclass(frozen=True)
class DeliveryResult:
    result: str
    setup_id: str
    publication_state: str | None = None
    publication_attempts: int | None = None
    published_at_iso: str | None = None
    next_attempt_at_iso: str | None = None
    last_error: str | None = None
    lease_token: str | None = None
    lease_owner_id: str | None = None
    last_attempt_at_iso: str | None = None
    detail: str | None = None


class OpeningRangeRetestEmissionStoreError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class OpeningRangeRetestEmissionStore:
    _schema_lock = threading.RLock()

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        lease_seconds: int | None = None,
    ) -> None:
        self.db_path = self._resolve_db_path(db_path)
        self.lease_seconds = _validate_lease_seconds(
            lease_seconds if lease_seconds is not None else self._configured_lease_seconds()
        )
        self._busy_timeout_ms = int(getattr(cfg, "TRADE_DB_BUSY_TIMEOUT_MS", 10000) or 10000)
        self._startup_error: tuple[str, str] | None = None
        try:
            self.init_schema()
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
            self._startup_error = (_classify_sqlite_error(exc), str(exc))

    @staticmethod
    def _configured_lease_seconds() -> Any:
        env_value = os.getenv("OPENING_RANGE_RETEST_PUBLICATION_LEASE_SECONDS")
        if env_value not in (None, ""):
            return env_value
        return getattr(cfg, "OPENING_RANGE_RETEST_PUBLICATION_LEASE_SECONDS", None)

    @staticmethod
    def _resolve_db_path(db_path: str | Path | None) -> Path:
        if db_path is not None:
            return ensure_parent_dir(Path(str(db_path)).expanduser())
        configured = str(getattr(cfg, "TRADE_DB_PATH", "") or "").strip()
        if configured:
            return ensure_parent_dir(Path(configured).expanduser())
        desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
        return ensure_parent_dir(trade_db_path(desk_id))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=5.0,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            with contextlib.suppress(Exception):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _unavailable_publication_result(self, setup_id: str) -> PublicationResult:
        code, detail = self._startup_error or ("OWNER_UNAVAILABLE", "store_initialization_failed")
        return PublicationResult(result=code, setup_id=setup_id, detail=detail)

    def _unavailable_lease_result(self, setup_id: str) -> LeaseResult:
        code, detail = self._startup_error or ("OWNER_UNAVAILABLE", "store_initialization_failed")
        return LeaseResult(result=code, setup_id=setup_id, detail=detail)

    def _unavailable_delivery_result(self, setup_id: str) -> DeliveryResult:
        code, detail = self._startup_error or ("OWNER_UNAVAILABLE", "store_initialization_failed")
        return DeliveryResult(result=code, setup_id=setup_id, detail=detail)

    def init_schema(self) -> None:
        with self._schema_lock:
            with self._connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS opening_range_retest_lineage (
                        setup_id TEXT PRIMARY KEY,
                        strategy_id TEXT NOT NULL,
                        contract_version TEXT NOT NULL,
                        schema_version INTEGER NOT NULL,
                        source_component TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        session_date TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        boundary_type TEXT NOT NULL,
                        normalized_boundary_value REAL NOT NULL,
                        breakout_timestamp_iso TEXT NOT NULL,
                        history_hash TEXT NOT NULL,
                        candidate_fingerprint TEXT NOT NULL,
                        state TEXT NOT NULL CHECK(state IN ('EMITTED','INVALIDATED','EXPIRED')),
                        created_at_iso TEXT NOT NULL,
                        emitted_at_iso TEXT,
                        invalidated_at_iso TEXT,
                        expired_at_iso TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS opening_range_retest_outbox (
                        outbox_id TEXT PRIMARY KEY,
                        setup_id TEXT NOT NULL UNIQUE,
                        candidate_payload_json TEXT NOT NULL,
                        candidate_fingerprint TEXT NOT NULL,
                        publication_state TEXT NOT NULL CHECK(publication_state IN ('PENDING','LEASED','PUBLISHED','RETRYABLE_FAILED','FAILED_FINAL')),
                        publication_attempts INTEGER NOT NULL DEFAULT 0,
                        created_at_iso TEXT NOT NULL,
                        next_attempt_at_iso TEXT,
                        published_at_iso TEXT,
                        last_attempt_at_iso TEXT,
                        last_error TEXT,
                        lease_token TEXT,
                        lease_owner_id TEXT,
                        lease_acquired_at_iso TEXT,
                        lease_expires_at_iso TEXT,
                        schema_version INTEGER NOT NULL,
                        FOREIGN KEY (setup_id) REFERENCES opening_range_retest_lineage(setup_id)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_orb_retest_lineage_session_symbol_state ON opening_range_retest_lineage(session_date, symbol, state)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_orb_retest_lineage_symbol_session_direction_state ON opening_range_retest_lineage(symbol, session_date, direction, state)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_orb_retest_lineage_strategy_session_state ON opening_range_retest_lineage(strategy_id, session_date, state)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_orb_retest_outbox_state_next_attempt ON opening_range_retest_outbox(publication_state, next_attempt_at_iso)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_orb_retest_outbox_state_lease_expiry ON opening_range_retest_outbox(publication_state, lease_expires_at_iso)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_orb_retest_outbox_lease_expiry ON opening_range_retest_outbox(lease_expires_at_iso)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_orb_retest_outbox_setup_id ON opening_range_retest_outbox(setup_id)")

    def _build_outbox_id(self, proposal: OpeningRangeRetestProposal) -> str:
        return f"outbox:{proposal.setup_id}"

    def _compare_immutable_fields(self, row: sqlite3.Row, proposal: OpeningRangeRetestProposal) -> bool:
        for key, value in proposal.immutable_items():
            current = row[key]
            if key == "normalized_boundary_value":
                if float(current) != float(value):
                    return False
                continue
            if str(current) != str(value):
                return False
        return True

    def _insert_lineage_row(
        self,
        conn: sqlite3.Connection,
        proposal: OpeningRangeRetestProposal,
        *,
        emitted_at_iso: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO opening_range_retest_lineage (
                setup_id,
                strategy_id,
                contract_version,
                schema_version,
                source_component,
                symbol,
                session_date,
                direction,
                boundary_type,
                normalized_boundary_value,
                breakout_timestamp_iso,
                history_hash,
                candidate_fingerprint,
                state,
                created_at_iso,
                emitted_at_iso,
                invalidated_at_iso,
                expired_at_iso
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'EMITTED', ?, ?, NULL, NULL)
            """,
            (
                proposal.setup_id,
                proposal.strategy_id,
                proposal.contract_version,
                proposal.schema_version,
                proposal.source_component,
                proposal.symbol,
                proposal.session_date,
                proposal.direction,
                proposal.boundary_type,
                proposal.normalized_boundary_value,
                proposal.breakout_timestamp_iso,
                proposal.history_hash,
                proposal.candidate_fingerprint,
                proposal.created_at_iso,
                emitted_at_iso,
            ),
        )

    def _insert_outbox_row(self, conn: sqlite3.Connection, proposal: OpeningRangeRetestProposal) -> None:
        conn.execute(
            """
            INSERT INTO opening_range_retest_outbox (
                outbox_id,
                setup_id,
                candidate_payload_json,
                candidate_fingerprint,
                publication_state,
                publication_attempts,
                created_at_iso,
                next_attempt_at_iso,
                published_at_iso,
                last_attempt_at_iso,
                last_error,
                lease_token,
                lease_owner_id,
                lease_acquired_at_iso,
                lease_expires_at_iso,
                schema_version
            ) VALUES (?, ?, ?, ?, 'PENDING', 0, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?)
            """,
            (
                self._build_outbox_id(proposal),
                proposal.setup_id,
                proposal.candidate_payload_json,
                proposal.candidate_fingerprint,
                proposal.created_at_iso,
                proposal.schema_version,
            ),
        )

    def _update_outbox_row(self, conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> int:
        conn.execute(sql, params)
        return int(conn.execute("SELECT changes()").fetchone()[0] or 0)

    def _validate_existing_states(self, lineage_row: sqlite3.Row | None, outbox_row: sqlite3.Row | None) -> str | None:
        if lineage_row is None or outbox_row is None:
            return "OWNER_STATE_CONFLICT"
        lineage_state = str(lineage_row["state"] or "").strip().upper()
        outbox_state = str(outbox_row["publication_state"] or "").strip().upper()
        if lineage_state not in LINEAGE_STATES or outbox_state not in OUTBOX_STATES:
            return "OWNER_STATE_CONFLICT"
        return None

    def _lineage_record(self, conn: sqlite3.Connection, setup_id: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM opening_range_retest_lineage WHERE setup_id=?",
            (setup_id,),
        ).fetchone()

    def _outbox_record(self, conn: sqlite3.Connection, setup_id: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM opening_range_retest_outbox WHERE setup_id=?",
            (setup_id,),
        ).fetchone()

    def get_lineage(self, setup_id: str) -> LineageRecord | None:
        key = _validate_non_empty(setup_id, "setup_id")
        if self._startup_error is not None:
            return None
        with self._connection() as conn:
            row = self._lineage_record(conn, key)
        return LineageRecord.from_row(row) if row is not None else None

    def get_outbox_record(self, setup_id: str) -> OutboxRecord | None:
        key = _validate_non_empty(setup_id, "setup_id")
        if self._startup_error is not None:
            return None
        with self._connection() as conn:
            row = self._outbox_record(conn, key)
        return OutboxRecord.from_row(row) if row is not None else None

    def accept_candidate_proposal(self, proposal: OpeningRangeRetestProposal) -> PublicationResult:
        if self._startup_error is not None:
            return self._unavailable_publication_result(proposal.setup_id)
        try:
            with self._transaction() as conn:
                existing_lineage = self._lineage_record(conn, proposal.setup_id)
                existing_outbox = self._outbox_record(conn, proposal.setup_id)
                if existing_lineage is not None or existing_outbox is not None:
                    state_error = self._validate_existing_states(existing_lineage, existing_outbox)
                    if state_error:
                        return PublicationResult(result=state_error, setup_id=proposal.setup_id, detail="malformed_durable_record")
                    if existing_lineage is None or existing_outbox is None:
                        return PublicationResult(result="OWNER_STATE_CONFLICT", setup_id=proposal.setup_id, detail="missing_companion_row")
                    if self._compare_immutable_fields(existing_lineage, proposal):
                        return PublicationResult(
                            result="ALREADY_EMITTED",
                            setup_id=proposal.setup_id,
                            lineage_state=str(existing_lineage["state"]),
                            publication_state=str(existing_outbox["publication_state"]),
                            publication_attempts=int(existing_outbox["publication_attempts"] or 0),
                            outbox_id=str(existing_outbox["outbox_id"]),
                        )
                    return PublicationResult(result="OWNER_STATE_CONFLICT", setup_id=proposal.setup_id, detail="immutable_mismatch")

                now_iso = _utc_now_iso()
                self._insert_lineage_row(conn, proposal, emitted_at_iso=now_iso)
                self._insert_outbox_row(conn, proposal)
                return PublicationResult(
                    result="ACCEPTED_FOR_PUBLICATION",
                    setup_id=proposal.setup_id,
                    lineage_state="EMITTED",
                    publication_state="PENDING",
                    publication_attempts=0,
                    outbox_id=self._build_outbox_id(proposal),
                )
        except sqlite3.OperationalError as exc:
            return PublicationResult(result=_classify_sqlite_error(exc), setup_id=proposal.setup_id, detail=str(exc))
        except sqlite3.DatabaseError as exc:
            return PublicationResult(result=_classify_sqlite_error(exc), setup_id=proposal.setup_id, detail=str(exc))
        except Exception as exc:
            if isinstance(exc, (ValueError, TypeError)):
                raise
            return PublicationResult(result="ERROR", setup_id=getattr(proposal, "setup_id", ""), detail=str(exc))

    def acquire_delivery_lease(self, *, setup_id: str, lease_owner_id: str, now_iso: str | None = None) -> LeaseResult:
        key = _validate_non_empty(setup_id, "setup_id")
        owner = _validate_non_empty(lease_owner_id, "lease_owner_id")
        now = now_iso or _utc_now_iso()
        _parse_iso8601(now, field_name="now_iso")
        lease_expires = (_utc_from_iso(now, field_name="now_iso") + timedelta(seconds=self.lease_seconds)).isoformat().replace("+00:00", "Z")
        lease_token = uuid.uuid4().hex
        if self._startup_error is not None:
            return self._unavailable_lease_result(key)
        try:
            with self._transaction() as conn:
                outbox = self._outbox_record(conn, key)
                lineage = self._lineage_record(conn, key)
                if lineage is None or outbox is None:
                    return LeaseResult(result="OWNER_STATE_CONFLICT", setup_id=key, detail="missing_companion_row")
                state_error = self._validate_existing_states(lineage, outbox)
                if state_error:
                    return LeaseResult(result=state_error, setup_id=key, detail="malformed_durable_record")

                state = str(outbox["publication_state"]).strip().upper()
                next_attempt = outbox["next_attempt_at_iso"]
                lease_expires_at = outbox["lease_expires_at_iso"]
                if state == "PUBLISHED":
                    return LeaseResult(result="ALREADY_PUBLISHED", setup_id=key, publication_state=state, publication_attempts=int(outbox["publication_attempts"] or 0))
                if state == "FAILED_FINAL":
                    return LeaseResult(result="NOT_DELIVERABLE", setup_id=key, publication_state=state, publication_attempts=int(outbox["publication_attempts"] or 0))

                eligible = False
                stale_lease_reclaimed = False
                if state == "PENDING":
                    eligible = next_attempt in (None, "") or str(next_attempt) <= now
                elif state == "RETRYABLE_FAILED":
                    eligible = next_attempt in (None, "") or str(next_attempt) <= now
                elif state == "LEASED":
                    if lease_expires_at is None:
                        return LeaseResult(result="OWNER_STATE_CONFLICT", setup_id=key, detail="missing_lease_expiry")
                    try:
                        expired = _utc_from_iso(str(lease_expires_at), field_name="lease_expires_at_iso") <= _utc_from_iso(now, field_name="now_iso")
                    except Exception:
                        return LeaseResult(result="OWNER_STATE_CONFLICT", setup_id=key, detail="invalid_lease_expiry")
                    eligible = expired
                    stale_lease_reclaimed = expired
                else:
                    return LeaseResult(result="OWNER_STATE_CONFLICT", setup_id=key, detail="unknown_publication_state")

                if not eligible:
                    return LeaseResult(result="LEASE_HELD", setup_id=key, publication_state=state, publication_attempts=int(outbox["publication_attempts"] or 0))

                rowcount = self._update_outbox_row(
                    conn,
                    """
                    UPDATE opening_range_retest_outbox
                    SET publication_state='LEASED',
                        lease_token=?,
                        lease_owner_id=?,
                        lease_acquired_at_iso=?,
                        lease_expires_at_iso=?
                    WHERE setup_id=?
                    """,
                    (lease_token, owner, now, lease_expires, key),
                )
                if int(rowcount or 0) != 1:
                    return LeaseResult(result="OWNER_STATE_CONFLICT", setup_id=key, detail="lease_update_failed")
                return LeaseResult(
                    result="LEASE_GRANTED",
                    setup_id=key,
                    publication_state="LEASED",
                    publication_attempts=int(outbox["publication_attempts"] or 0),
                    lease_token=lease_token,
                    lease_owner_id=owner,
                    lease_acquired_at_iso=now,
                    lease_expires_at_iso=lease_expires,
                    stale_lease_reclaimed=stale_lease_reclaimed,
                )
        except sqlite3.OperationalError as exc:
            return LeaseResult(result=_classify_sqlite_error(exc), setup_id=key, detail=str(exc))
        except sqlite3.DatabaseError as exc:
            return LeaseResult(result=_classify_sqlite_error(exc), setup_id=key, detail=str(exc))

    def record_delivery_start(self, *, setup_id: str, lease_token: str, lease_owner_id: str, now_iso: str | None = None) -> DeliveryResult:
        key = _validate_non_empty(setup_id, "setup_id")
        token = _validate_non_empty(lease_token, "lease_token")
        owner = _validate_non_empty(lease_owner_id, "lease_owner_id")
        now = now_iso or _utc_now_iso()
        _parse_iso8601(now, field_name="now_iso")
        if self._startup_error is not None:
            return self._unavailable_delivery_result(key)
        try:
            with self._transaction() as conn:
                row = self._outbox_record(conn, key)
                if row is None:
                    return DeliveryResult(result="OWNER_STATE_CONFLICT", setup_id=key, detail="missing_outbox_row")
                if self._validate_existing_states(self._lineage_record(conn, key), row):
                    return DeliveryResult(result="OWNER_STATE_CONFLICT", setup_id=key, detail="malformed_durable_record")
                if str(row["publication_state"]).strip().upper() != "LEASED":
                    return DeliveryResult(result="OWNER_STATE_CONFLICT", setup_id=key, publication_state=str(row["publication_state"]), detail="delivery_start_requires_leased")
                if str(row["lease_token"] or "") != token or str(row["lease_owner_id"] or "") != owner:
                    return DeliveryResult(result="OWNER_STATE_CONFLICT", setup_id=key, publication_state="LEASED", detail="lease_token_or_owner_mismatch")
                attempts = int(row["publication_attempts"] or 0)
                last_attempt_at_iso = str(row["last_attempt_at_iso"] or "")
                if last_attempt_at_iso and str(row["lease_token"] or "") == token and str(row["lease_owner_id"] or "") == owner:
                    return DeliveryResult(
                        result="DELIVERY_STARTED",
                        setup_id=key,
                        publication_state="LEASED",
                        publication_attempts=attempts,
                        lease_token=token,
                        lease_owner_id=owner,
                        last_attempt_at_iso=last_attempt_at_iso,
                    )
                attempts += 1
                conn.execute(
                    """
                    UPDATE opening_range_retest_outbox
                    SET publication_attempts=?,
                        last_attempt_at_iso=?
                    WHERE setup_id=?
                    """,
                    (attempts, now, key),
                )
                return DeliveryResult(
                    result="DELIVERY_STARTED",
                    setup_id=key,
                    publication_state="LEASED",
                    publication_attempts=attempts,
                    lease_token=token,
                    lease_owner_id=owner,
                    last_attempt_at_iso=now,
                )
        except sqlite3.OperationalError as exc:
            return DeliveryResult(result=_classify_sqlite_error(exc), setup_id=key, detail=str(exc))
        except sqlite3.DatabaseError as exc:
            return DeliveryResult(result=_classify_sqlite_error(exc), setup_id=key, detail=str(exc))

    def record_delivery_success(self, *, setup_id: str, lease_token: str, lease_owner_id: str, now_iso: str | None = None) -> DeliveryResult:
        return self._finalize_delivery(
            setup_id=setup_id,
            lease_token=lease_token,
            lease_owner_id=lease_owner_id,
            result_state="PUBLISHED",
            result_code="DELIVERED",
            now_iso=now_iso,
        )

    def record_retryable_failure(
        self,
        *,
        setup_id: str,
        lease_token: str,
        lease_owner_id: str,
        last_error: str,
        next_attempt_at_iso: str | None = None,
        now_iso: str | None = None,
    ) -> DeliveryResult:
        now = now_iso or _utc_now_iso()
        _parse_iso8601(now, field_name="now_iso")
        next_attempt = next_attempt_at_iso
        if next_attempt is None:
            next_attempt = (
                datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(seconds=self.lease_seconds)
            ).isoformat().replace("+00:00", "Z")
        _parse_iso8601(next_attempt, field_name="next_attempt_at_iso")
        return self._finalize_delivery(
            setup_id=setup_id,
            lease_token=lease_token,
            lease_owner_id=lease_owner_id,
            result_state="RETRYABLE_FAILED",
            result_code="RETRYABLE_FAILED",
            last_error=last_error,
            next_attempt_at_iso=next_attempt,
            now_iso=now,
        )

    def record_terminal_failure(
        self,
        *,
        setup_id: str,
        lease_token: str,
        lease_owner_id: str,
        last_error: str,
        now_iso: str | None = None,
    ) -> DeliveryResult:
        return self._finalize_delivery(
            setup_id=setup_id,
            lease_token=lease_token,
            lease_owner_id=lease_owner_id,
            result_state="FAILED_FINAL",
            result_code="FAILED_FINAL",
            last_error=last_error,
            now_iso=now_iso,
        )

    def _finalize_delivery(
        self,
        *,
        setup_id: str,
        lease_token: str,
        lease_owner_id: str,
        result_state: str,
        result_code: str,
        last_error: str | None = None,
        next_attempt_at_iso: str | None = None,
        now_iso: str | None = None,
    ) -> DeliveryResult:
        key = _validate_non_empty(setup_id, "setup_id")
        token = _validate_non_empty(lease_token, "lease_token")
        owner = _validate_non_empty(lease_owner_id, "lease_owner_id")
        now = now_iso or _utc_now_iso()
        _parse_iso8601(now, field_name="now_iso")
        if next_attempt_at_iso is not None:
            _parse_iso8601(next_attempt_at_iso, field_name="next_attempt_at_iso")
        if self._startup_error is not None:
            return self._unavailable_delivery_result(key)
        try:
            with self._transaction() as conn:
                row = self._outbox_record(conn, key)
                lineage = self._lineage_record(conn, key)
                if row is None or lineage is None:
                    return DeliveryResult(result="OWNER_STATE_CONFLICT", setup_id=key, detail="missing_companion_row")
                if self._validate_existing_states(lineage, row):
                    return DeliveryResult(result="OWNER_STATE_CONFLICT", setup_id=key, detail="malformed_durable_record")
                if str(row["publication_state"]).strip().upper() != "LEASED":
                    if str(row["publication_state"]).strip().upper() == "PUBLISHED":
                        return DeliveryResult(result="ALREADY_PUBLISHED", setup_id=key, publication_state="PUBLISHED", publication_attempts=int(row["publication_attempts"] or 0))
                    if str(row["publication_state"]).strip().upper() == "FAILED_FINAL":
                        return DeliveryResult(result="FAILED_FINAL", setup_id=key, publication_state="FAILED_FINAL", publication_attempts=int(row["publication_attempts"] or 0))
                    return DeliveryResult(result="OWNER_STATE_CONFLICT", setup_id=key, detail="delivery_requires_leased")
                if str(row["lease_token"] or "") != token or str(row["lease_owner_id"] or "") != owner:
                    return DeliveryResult(result="OWNER_STATE_CONFLICT", setup_id=key, publication_state="LEASED", detail="lease_token_or_owner_mismatch")
                attempts = int(row["publication_attempts"] or 0)
                update_sql = """
                    UPDATE opening_range_retest_outbox
                    SET publication_state=?,
                        published_at_iso=?,
                        next_attempt_at_iso=?,
                        last_error=?,
                        lease_token=NULL,
                        lease_owner_id=NULL,
                        lease_acquired_at_iso=NULL,
                        lease_expires_at_iso=NULL
                    WHERE setup_id=?
                """
                published_at = None
                if result_state == "PUBLISHED":
                    published_at = now
                    next_attempt = None
                    error_text = None
                elif result_state == "RETRYABLE_FAILED":
                    next_attempt = next_attempt_at_iso
                    error_text = str(last_error or "")
                else:
                    published_at = None
                    next_attempt = None
                    error_text = str(last_error or "")
                conn.execute(
                    update_sql,
                    (result_state, published_at, next_attempt, error_text, key),
                )
                return DeliveryResult(
                    result=result_code,
                    setup_id=key,
                    publication_state=result_state,
                    publication_attempts=attempts,
                    published_at_iso=published_at,
                    next_attempt_at_iso=next_attempt_at_iso if result_state == "RETRYABLE_FAILED" else None,
                    last_error=error_text,
                    lease_token=token,
                    lease_owner_id=owner,
                    last_attempt_at_iso=row["last_attempt_at_iso"],
                )
        except sqlite3.OperationalError as exc:
            return DeliveryResult(result=_classify_sqlite_error(exc), setup_id=key, detail=str(exc))
        except sqlite3.DatabaseError as exc:
            return DeliveryResult(result=_classify_sqlite_error(exc), setup_id=key, detail=str(exc))


@contextmanager
def create_isolated_replay_store(*, lease_seconds: int | None = None) -> Iterator[OpeningRangeRetestEmissionStore]:
    with tempfile.TemporaryDirectory(prefix="opening_range_retest_emission_store_") as tmpdir:
        db_path = Path(tmpdir) / "opening_range_retest_emission_store.sqlite"
        store = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=lease_seconds)
        yield store


__all__ = [
    "DeliveryResult",
    "IMMUTABLE_LINEAGE_FIELDS",
    "LeaseResult",
    "LINEAGE_STATES",
    "OpeningRangeRetestEmissionStore",
    "OpeningRangeRetestEmissionStoreError",
    "OpeningRangeRetestProposal",
    "OutboxRecord",
    "OUTBOX_STATES",
    "PublicationResult",
    "create_isolated_replay_store",
]

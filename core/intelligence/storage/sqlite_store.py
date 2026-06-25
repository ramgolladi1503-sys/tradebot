import sqlite3
import logging
from typing import Optional
from core.intelligence.config import config

logger = logging.getLogger(__name__)

class MIPSQLiteStore:
    """
    Hardened SQLite storage for the Market Intelligence Platform.
    Replaces the local flat-file storage with a robust structured schema.
    """
    def __init__(self, db_path: str = config.SQLITE_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Mirroring TradeBot's persistence robustness
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            # intelligence_sources
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intelligence_sources (
                    source_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    parser_version TEXT,
                    extraction_version TEXT
                )
            """)

            # intelligence_fetch_runs
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intelligence_fetch_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    fetch_timestamp REAL NOT NULL,
                    status TEXT NOT NULL,
                    http_status INTEGER,
                    failure_reason TEXT,
                    latency REAL,
                    content_hash TEXT,
                    FOREIGN KEY(source_id) REFERENCES intelligence_sources(source_id)
                )
            """)

            # intelligence_documents
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intelligence_documents (
                    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    title TEXT,
                    published_timestamp REAL,
                    raw_content TEXT,
                    FOREIGN KEY(run_id) REFERENCES intelligence_fetch_runs(run_id)
                )
            """)

            # intelligence_events (Extracted items)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intelligence_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id INTEGER NOT NULL,
                    advisory_only BOOLEAN DEFAULT 1,
                    calibration_status TEXT NOT NULL,
                    evidence_pointer TEXT,
                    FOREIGN KEY(doc_id) REFERENCES intelligence_documents(doc_id)
                )
            """)

            # intelligence_factors (The granular metrics broken down)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intelligence_factors (
                    factor_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    calibration_status TEXT NOT NULL,
                    FOREIGN KEY(event_id) REFERENCES intelligence_events(event_id)
                )
            """)

    def insert_fetch_run(self, source_id: str, url: str, timestamp: float, status: str, 
                         latency: float, http_status: Optional[int] = None, failure_reason: Optional[str] = None, 
                         content_hash: Optional[str] = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO intelligence_fetch_runs
                (source_id, url, fetch_timestamp, status, http_status, failure_reason, latency, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (source_id, url, timestamp, status, http_status, failure_reason, latency, content_hash))
            return cursor.lastrowid or 0

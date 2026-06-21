import json
import logging
import sqlite3
import uuid
from typing import Any
from pathlib import Path
from config import config as cfg
from core.fs_utils import ensure_parent_dir
from core.paths import logs_dir

logger = logging.getLogger(__name__)

_TELEMETRY_COUNTERS = {
    "ranking_snapshot_seen": 0,
    "ranking_snapshot_written": 0,
    "ranking_snapshot_failed": 0,
}

_RANKING_SNAPSHOT_JSONL = Path(getattr(cfg, "RANKING_SNAPSHOT_LOG_PATH", str(logs_dir() / "ranking_snapshots.jsonl")))

def _conn():
    db_path = ensure_parent_dir(Path(str(cfg.TRADE_DB_PATH)))
    return sqlite3.connect(str(db_path))

def _init_db():
    with _conn() as conn:
        conn.execute(
            """
        CREATE TABLE IF NOT EXISTS ranking_snapshots (
            cycle_id TEXT,
            timestamp REAL,
            symbol TEXT,
            instrument_id TEXT,
            strategy_id TEXT,
            rank_position INTEGER,
            side TEXT,
            strike REAL,
            expiry TEXT,
            option_type TEXT,
            trade_score REAL,
            confidence REAL,
            final_score REAL,
            spread_pct REAL,
            quote_age_sec REAL,
            regime TEXT,
            execution_allowed INTEGER,
            gatekeeper_allowed INTEGER,
            veto_reasons TEXT,
            underlying_spot REAL,
            option_ltp REAL,
            bid REAL,
            ask REAL
        )
            """
        )

# Initialize on import
try:
    _init_db()
except Exception as e:
    logger.warning("Failed to initialize ranking_snapshots table: %s", e)


def log_ranking_snapshots(candidates: list[dict[str, Any]]) -> None:
    """
    Safely captures the entire cycle of ranked candidates for outcome replay analysis.
    Executes entirely outside the critical path, ignoring persistence compression.
    """
    if not candidates or len(candidates) < 2:
        return

    _TELEMETRY_COUNTERS["ranking_snapshot_seen"] += 1

    try:
        cycle_id = str(uuid.uuid4())
        
        snapshots = []
        for i, cand in enumerate(candidates):
            rank_position = i + 1
            
            # Deep copy / new dict construction for immutability
            vetos = list(cand.get("gate_reasons") or [])
            if cand.get("reject_reason"):
                vetos.append(cand.get("reject_reason"))
            
            snapshot = {
                "cycle_id": cycle_id,
                "timestamp": cand.get("timestamp_epoch") or cand.get("timestamp"),
                "symbol": cand.get("symbol") or cand.get("underlying"),
                "instrument_id": cand.get("instrument_id") or cand.get("instrument"),
                "strategy_id": cand.get("strategy_id"),
                "rank_position": rank_position,
                "side": cand.get("side") or cand.get("direction"),
                "strike": cand.get("strike"),
                "expiry": cand.get("expiry") or cand.get("expiry_date"),
                "option_type": cand.get("option_type"),
                "trade_score": cand.get("trade_score") or cand.get("score_0_100"),
                "confidence": cand.get("confidence") or cand.get("xgb_proba"),
                "final_score": cand.get("final_score") or cand.get("trade_score") or cand.get("score_0_100"),
                "spread_pct": cand.get("spread_pct"),
                "quote_age_sec": cand.get("quote_age_sec") or cand.get("quote_age"),
                "regime": cand.get("regime"),
                "execution_allowed": bool(cand.get("execution_allowed")),
                "gatekeeper_allowed": cand.get("gatekeeper_allowed", 0),
                "veto_reasons": " | ".join(map(str, vetos)),
                "underlying_spot": cand.get("underlying_spot"),
                "option_ltp": cand.get("option_ltp") or cand.get("last_price"),
                "bid": cand.get("bid"),
                "ask": cand.get("ask")
            }
            snapshots.append(snapshot)

        # Write to JSONL
        _RANKING_SNAPSHOT_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with _RANKING_SNAPSHOT_JSONL.open("a") as f:
            for s in snapshots:
                f.write(json.dumps(s) + "\n")

        # Write to SQLite
        with _conn() as conn:
            conn.executemany(
                """
                INSERT INTO ranking_snapshots (
                    cycle_id, timestamp, symbol, instrument_id, strategy_id, rank_position,
                    side, strike, expiry, option_type, trade_score, confidence, final_score,
                    spread_pct, quote_age_sec, regime, execution_allowed, gatekeeper_allowed,
                    veto_reasons, underlying_spot, option_ltp, bid, ask
                ) VALUES (
                    :cycle_id, :timestamp, :symbol, :instrument_id, :strategy_id, :rank_position,
                    :side, :strike, :expiry, :option_type, :trade_score, :confidence, :final_score,
                    :spread_pct, :quote_age_sec, :regime, :execution_allowed, :gatekeeper_allowed,
                    :veto_reasons, :underlying_spot, :option_ltp, :bid, :ask
                )
                """,
                snapshots
            )
        
        _TELEMETRY_COUNTERS["ranking_snapshot_written"] += 1

    except Exception as e:
        _TELEMETRY_COUNTERS["ranking_snapshot_failed"] += 1
        if _TELEMETRY_COUNTERS["ranking_snapshot_failed"] % 10 == 1:
            logger.warning("Ranking snapshot write failed (error=%s). Failures: %d", e, _TELEMETRY_COUNTERS["ranking_snapshot_failed"])

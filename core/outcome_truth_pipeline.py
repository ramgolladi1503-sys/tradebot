"""Migration note:
Centralized outcome/truth pipeline for acceptance and ops gates.
This module keeps data-truth checks deterministic and mode-aware.
"""

from __future__ import annotations

from core.paths import data_root, logs_dir
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import config as cfg
from core.time_utils import now_ist, now_utc_epoch


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:  # NaN
            return None
        return out
    except Exception:
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _status_paths(day: str) -> tuple[Path, Path]:
    latest = Path(getattr(cfg, "OUTCOME_TRUTH_STATUS_PATH", str(logs_dir() / "outcome_truth_status_latest.json")))
    if latest.name.endswith(".json") and "latest" in latest.name:
        day_path = latest.with_name(f"outcome_truth_status_{day}.json")
        return day_path, latest
    latest_path = latest if latest.suffix == ".json" else (latest / "outcome_truth_status_latest.json")
    day_path = latest_path.with_name(f"outcome_truth_status_{day}.json")
    return day_path, latest_path


def _ensure_outcomes_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS outcomes (
            trade_id TEXT,
            exit_price REAL,
            exit_time TEXT,
            actual INTEGER,
            r_multiple REAL,
            r_label INTEGER,
            exit_reason TEXT,
            realized_pnl REAL,
            r_multiple_realized REAL,
            outcome_label TEXT,
            outcome_grade TEXT,
            timestamp_epoch REAL,
            timestamp_iso TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_outcomes_trade_ts
        ON outcomes(trade_id, timestamp_epoch)
        """
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (str(table),),
    )
    return cur.fetchone() is not None


def _derive_outcome_label(realized_pnl: float | None, epsilon: float) -> str | None:
    if realized_pnl is None:
        return None
    if realized_pnl > float(epsilon):
        return "WIN"
    if realized_pnl < -float(epsilon):
        return "LOSS"
    return "BREAKEVEN"


def reconcile_outcomes_from_trades(
    db_path: Path,
    *,
    start_epoch: float,
    epsilon: float | None = None,
) -> dict[str, Any]:
    status = {
        "ok": True,
        "reason_code": "OK",
        "db_path": str(db_path),
        "start_epoch": float(start_epoch),
        "scanned": 0,
        "upserted": 0,
        "decision_outcome_updates": 0,
    }
    if not db_path.exists():
        status.update({"ok": False, "reason_code": "TRADE_DB_MISSING"})
        return status
    eps = float(epsilon if epsilon is not None else getattr(cfg, "OUTCOME_PNL_EPSILON", 1e-6))
    try:
        with sqlite3.connect(str(db_path)) as conn:
            _ensure_outcomes_schema(conn)
            if not _table_exists(conn, "trades"):
                status.update({"ok": False, "reason_code": "TRADES_TABLE_MISSING"})
                return status
            cur = conn.execute(
                """
                SELECT
                    trade_id,
                    exit_price,
                    exit_time,
                    exit_reason,
                    realized_pnl,
                    r_multiple_realized,
                    outcome_label,
                    outcome_grade,
                    timestamp_epoch,
                    timestamp_iso
                FROM trades
                WHERE timestamp_epoch IS NOT NULL
                  AND timestamp_epoch >= ?
                  AND trade_id IS NOT NULL
                  AND (
                    r_multiple_realized IS NOT NULL
                    OR realized_pnl IS NOT NULL
                    OR outcome_label IS NOT NULL
                  )
                ORDER BY timestamp_epoch ASC
                """,
                (float(start_epoch),),
            )
            rows = cur.fetchall()
            status["scanned"] = int(len(rows))
            if rows:
                upsert_rows = []
                for (
                    trade_id,
                    exit_price,
                    exit_time,
                    exit_reason,
                    realized_pnl,
                    r_multiple_realized,
                    outcome_label,
                    outcome_grade,
                    timestamp_epoch,
                    timestamp_iso,
                ) in rows:
                    ts_epoch = _coerce_float(timestamp_epoch)
                    if ts_epoch is None:
                        continue
                    ts_iso = str(timestamp_iso or "")
                    if not ts_iso:
                        try:
                            ts_iso = (
                                datetime.fromtimestamp(float(ts_epoch), tz=timezone.utc)
                                .isoformat()
                                .replace("+00:00", "Z")
                            )
                        except Exception:
                            ts_iso = str(exit_time or "")
                    pnl = _coerce_float(realized_pnl)
                    r_mult = _coerce_float(r_multiple_realized)
                    label = str(outcome_label or "").strip().upper() or _derive_outcome_label(pnl, eps)
                    actual = None
                    if label == "WIN":
                        actual = 1
                    elif label == "LOSS":
                        actual = 0
                    elif label == "BREAKEVEN":
                        actual = 0
                    upsert_rows.append(
                        (
                            str(trade_id),
                            _coerce_float(exit_price),
                            str(exit_time or ts_iso),
                            _coerce_int(actual),
                            r_mult,
                            _coerce_int(1 if (r_mult is not None and r_mult >= 1.0) else 0 if r_mult is not None else None),
                            str(exit_reason or ""),
                            pnl,
                            r_mult,
                            label,
                            str(outcome_grade or ""),
                            float(ts_epoch),
                            ts_iso,
                        )
                    )
                if upsert_rows:
                    before_changes = int(conn.total_changes)
                    conn.executemany(
                        """
                        INSERT INTO outcomes (
                            trade_id,
                            exit_price,
                            exit_time,
                            actual,
                            r_multiple,
                            r_label,
                            exit_reason,
                            realized_pnl,
                            r_multiple_realized,
                            outcome_label,
                            outcome_grade,
                            timestamp_epoch,
                            timestamp_iso
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(trade_id, timestamp_epoch) DO UPDATE SET
                            exit_price = COALESCE(excluded.exit_price, outcomes.exit_price),
                            exit_time = COALESCE(NULLIF(excluded.exit_time, ''), outcomes.exit_time),
                            actual = COALESCE(excluded.actual, outcomes.actual),
                            r_multiple = COALESCE(excluded.r_multiple, outcomes.r_multiple),
                            r_label = COALESCE(excluded.r_label, outcomes.r_label),
                            exit_reason = COALESCE(NULLIF(excluded.exit_reason, ''), outcomes.exit_reason),
                            realized_pnl = COALESCE(excluded.realized_pnl, outcomes.realized_pnl),
                            r_multiple_realized = COALESCE(excluded.r_multiple_realized, outcomes.r_multiple_realized),
                            outcome_label = COALESCE(NULLIF(excluded.outcome_label, ''), outcomes.outcome_label),
                            outcome_grade = COALESCE(NULLIF(excluded.outcome_grade, ''), outcomes.outcome_grade),
                            timestamp_iso = COALESCE(NULLIF(excluded.timestamp_iso, ''), outcomes.timestamp_iso)
                        """,
                        upsert_rows,
                    )
                    status["upserted"] = int(max(0, conn.total_changes - before_changes))
            if _table_exists(conn, "decision_events"):
                dec_cols_cur = conn.execute("PRAGMA table_info(decision_events)")
                dec_cols = {str(row[1]) for row in dec_cols_cur.fetchall()}
                update_clauses: list[str] = []
                if "realized_pnl" in dec_cols:
                    update_clauses.append(
                        """
                        realized_pnl = COALESCE(
                            realized_pnl,
                            (
                                SELECT o.realized_pnl
                                FROM outcomes o
                                WHERE o.trade_id = decision_events.trade_id
                                ORDER BY o.timestamp_epoch DESC
                                LIMIT 1
                            )
                        )
                        """
                    )
                if "pnl_horizon_15m" in dec_cols:
                    update_clauses.append(
                        """
                        pnl_horizon_15m = COALESCE(
                            pnl_horizon_15m,
                            (
                                SELECT o.r_multiple
                                FROM outcomes o
                                WHERE o.trade_id = decision_events.trade_id
                                ORDER BY o.timestamp_epoch DESC
                                LIMIT 1
                            )
                        )
                        """
                    )
                if "filled_bool" in dec_cols:
                    update_clauses.append(
                        """
                        filled_bool = COALESCE(
                            filled_bool,
                            CASE
                                WHEN EXISTS (
                                    SELECT 1
                                    FROM outcomes o
                                    WHERE o.trade_id = decision_events.trade_id
                                ) THEN 1
                                ELSE filled_bool
                            END
                        )
                        """
                    )
                if update_clauses:
                    before_updates = int(conn.total_changes)
                    try:
                        conn.execute(
                            f"""
                            UPDATE decision_events
                            SET {", ".join(update_clauses)}
                            WHERE timestamp_epoch IS NOT NULL
                              AND timestamp_epoch >= ?
                              AND trade_id IS NOT NULL
                            """,
                            (float(start_epoch),),
                        )
                        status["decision_outcome_updates"] = int(max(0, conn.total_changes - before_updates))
                    except Exception as exc:
                        status["decision_outcome_update_error"] = f"{type(exc).__name__}"
            conn.commit()
    except Exception as exc:
        status.update({"ok": False, "reason_code": f"OUTCOME_RECONCILE_ERROR:{type(exc).__name__}"})
    return status


def _truth_dataset_row_count(truth_path: Path) -> tuple[int, str]:
    if not truth_path.exists():
        return 0, "missing"
    try:
        df = pd.read_parquet(truth_path)
    except Exception as exc:
        return 0, f"unreadable:{type(exc).__name__}"
    return int(len(df)), "ok" if len(df) > 0 else "empty"


def rebuild_truth_dataset(
    *,
    truth_path: Path,
    decision_jsonl: Path,
    decision_sqlite: Path,
) -> dict[str, Any]:
    from ml.truth_dataset import build_truth_dataset

    out = {
        "ok": True,
        "reason_code": "OK",
        "truth_path": str(truth_path),
        "rows": 0,
        "source": "decision_events",
    }
    truth_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df, report = build_truth_dataset(
            decision_jsonl=decision_jsonl,
            decision_sqlite=decision_sqlite,
            out_parquet=truth_path,
        )
        out["rows"] = int(len(df))
        out["build_report"] = dict(report or {})
    except FileNotFoundError:
        # Deterministic empty schema fallback: do not crash ops on fresh installs.
        empty_df = pd.DataFrame(
            {
                "champion_proba": pd.Series(dtype="float64"),
                "challenger_proba": pd.Series(dtype="float64"),
                "pnl_15m": pd.Series(dtype="float64"),
            }
        )
        empty_df.to_parquet(truth_path, index=False)
        out.update({"ok": False, "reason_code": "NO_DECISION_EVENTS", "rows": 0, "source": "empty_schema"})
    except Exception as exc:
        out.update({"ok": False, "reason_code": f"TRUTH_BUILD_ERROR:{type(exc).__name__}"})
    return out


def _collect_counts(db_path: Path, *, start_epoch: float) -> dict[str, Any]:
    out = {
        "decision_rows": 0,
        "decision_rows_with_outcome": 0,
        "outcome_rows": 0,
        "outcome_link_rate": None,
    }
    if not db_path.exists():
        return out
    try:
        with sqlite3.connect(str(db_path)) as conn:
            if _table_exists(conn, "outcomes"):
                col_cur = conn.execute("PRAGMA table_info(outcomes)")
                cols = {str(row[1]) for row in col_cur.fetchall()}
                metric_cols = [c for c in ("r_multiple", "r_multiple_realized", "realized_pnl") if c in cols]
                if not metric_cols:
                    metric_cols = ["r_multiple"]
                metric_expr = " OR ".join([f"{col} IS NOT NULL" for col in metric_cols])
                cur = conn.execute(
                    f"""
                    SELECT COUNT(1)
                    FROM outcomes
                    WHERE timestamp_epoch IS NOT NULL
                      AND timestamp_epoch >= ?
                      AND ({metric_expr})
                    """,
                    (float(start_epoch),),
                )
                out["outcome_rows"] = int((cur.fetchone() or [0])[0] or 0)
            if _table_exists(conn, "decision_events"):
                cur = conn.execute(
                    """
                    SELECT COUNT(1)
                    FROM decision_events
                    WHERE timestamp_epoch IS NOT NULL
                      AND timestamp_epoch >= ?
                    """,
                    (float(start_epoch),),
                )
                decision_rows = int((cur.fetchone() or [0])[0] or 0)
                out["decision_rows"] = decision_rows
                if decision_rows > 0:
                    cur = conn.execute(
                        """
                        SELECT COUNT(DISTINCT d.trade_id)
                        FROM decision_events d
                        LEFT JOIN outcomes o
                          ON o.trade_id = d.trade_id
                         AND o.timestamp_epoch IS NOT NULL
                         AND o.timestamp_epoch >= ?
                        WHERE d.timestamp_epoch IS NOT NULL
                          AND d.timestamp_epoch >= ?
                          AND (
                            d.pnl_horizon_15m IS NOT NULL
                            OR d.realized_pnl IS NOT NULL
                            OR o.trade_id IS NOT NULL
                          )
                        """,
                        (float(start_epoch), float(start_epoch)),
                    )
                    linked = int((cur.fetchone() or [0])[0] or 0)
                    out["decision_rows_with_outcome"] = linked
                    out["outcome_link_rate"] = float(linked / max(decision_rows, 1))
    except Exception:
        return out
    return out


def assess_outcome_truth(
    *,
    strict: bool = False,
    now_epoch: float | None = None,
    db_path: Path | None = None,
    truth_path: Path | None = None,
) -> dict[str, Any]:
    now_ts = float(now_epoch if now_epoch is not None else now_utc_epoch())
    window_days = max(1, int(getattr(cfg, "ACCEPTANCE_WINDOW_DAYS", 30)))
    start_epoch = now_ts - float(window_days * 86400.0)
    db = Path(db_path or getattr(cfg, "TRADE_DB_PATH", str(data_root() / "trades.db")))
    truth = Path(truth_path or getattr(cfg, "TRUTH_DATASET_PATH", str(data_root() / "truth_dataset.parquet")))

    min_outcome_rows = max(
        1,
        int(
            getattr(
                cfg,
                "ACCEPTANCE_MIN_OUTCOME_ROWS",
                getattr(cfg, "ACCEPTANCE_MIN_TRADES", 20),
            )
        ),
    )
    min_shadow_rows = max(1, int(getattr(cfg, "ACCEPTANCE_MIN_SHADOW_ROWS", 100)))
    min_link_rate = float(getattr(cfg, "ACCEPTANCE_MIN_OUTCOME_LINK_RATE", 0.95))
    min_decision_rows_for_link = max(
        1,
        int(getattr(cfg, "ACCEPTANCE_MIN_DECISION_ROWS_FOR_LINK_RATE", 100)),
    )

    counts = _collect_counts(db, start_epoch=start_epoch)
    shadow_rows, shadow_state = _truth_dataset_row_count(truth)

    blockers: list[str] = []
    warnings: list[str] = []

    if int(counts.get("outcome_rows", 0)) < min_outcome_rows:
        blockers.append("OUTCOME_ROWS_INSUFFICIENT")
    if int(shadow_rows) < min_shadow_rows:
        blockers.append("SHADOW_ROWS_INSUFFICIENT")
    decision_rows = int(counts.get("decision_rows", 0))
    link_rate = counts.get("outcome_link_rate")
    if (
        decision_rows >= min_decision_rows_for_link
        and link_rate is not None
        and float(link_rate) < min_link_rate
    ):
        blockers.append("OUTCOME_LINK_RATE_BELOW_THRESHOLD")

    status = "PASS"
    if blockers and strict:
        status = "FAIL"
    elif blockers:
        status = "DEGRADED"
        warnings = list(blockers)

    return {
        "status": status,
        "strict": bool(strict),
        "ok": bool(status == "PASS"),
        "date": now_ist().date().isoformat(),
        "window_days": int(window_days),
        "start_epoch": float(start_epoch),
        "end_epoch": float(now_ts),
        "blockers": blockers,
        "warnings": warnings,
        "thresholds": {
            "min_outcome_rows": int(min_outcome_rows),
            "min_shadow_rows": int(min_shadow_rows),
            "min_outcome_link_rate": float(min_link_rate),
            "min_decision_rows_for_link_rate": int(min_decision_rows_for_link),
        },
        "metrics": {
            **counts,
            "shadow_rows": int(shadow_rows),
            "shadow_state": shadow_state,
        },
        "sources": {
            "trade_db_path": str(db),
            "truth_dataset_path": str(truth),
        },
    }


def run_outcome_truth_pipeline(
    *,
    strict: bool = False,
    now_epoch: float | None = None,
    db_path: Path | None = None,
    truth_path: Path | None = None,
    refresh: bool = True,
    write_status: bool = True,
) -> dict[str, Any]:
    now_ts = float(now_epoch if now_epoch is not None else now_utc_epoch())
    window_days = max(1, int(getattr(cfg, "ACCEPTANCE_WINDOW_DAYS", 30)))
    start_epoch = now_ts - float(window_days * 86400.0)
    db = Path(db_path or getattr(cfg, "TRADE_DB_PATH", str(data_root() / "trades.db")))
    truth = Path(truth_path or getattr(cfg, "TRUTH_DATASET_PATH", str(data_root() / "truth_dataset.parquet")))
    decision_jsonl = Path(getattr(cfg, "DECISION_LOG_PATH", str(logs_dir() / "decision_events.jsonl")))

    reconcile_meta = {
        "ok": True,
        "reason_code": "SKIPPED",
        "scanned": 0,
        "upserted": 0,
        "decision_outcome_updates": 0,
    }
    truth_meta = {
        "ok": True,
        "reason_code": "SKIPPED",
        "rows": None,
    }
    if refresh and bool(getattr(cfg, "OUTCOME_RECONCILE_ENABLE", True)):
        reconcile_meta = reconcile_outcomes_from_trades(
            db_path=db,
            start_epoch=float(start_epoch),
        )
        truth_meta = rebuild_truth_dataset(
            truth_path=truth,
            decision_jsonl=decision_jsonl,
            decision_sqlite=db,
        )

    assessment = assess_outcome_truth(
        strict=bool(strict),
        now_epoch=now_ts,
        db_path=db,
        truth_path=truth,
    )
    payload = {
        **assessment,
        "refresh": bool(refresh),
        "reconcile": reconcile_meta,
        "truth_refresh": truth_meta,
    }
    if write_status:
        day = str(payload.get("date") or now_ist().date().isoformat())
        day_path, latest_path = _status_paths(day)
        body = json.dumps(payload, indent=2, default=str)
        day_path.parent.mkdir(parents=True, exist_ok=True)
        day_path.write_text(body, encoding="utf-8")
        latest_path.write_text(body, encoding="utf-8")
        payload["status_path"] = str(latest_path)
        payload["status_day_path"] = str(day_path)
    return payload

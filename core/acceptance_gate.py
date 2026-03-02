"""Migration note:
Rolling statistical acceptance gate for PAPER/LIVE-shadow quality checks.
Gate stays observable in non-strict modes and fail-closed in strict LIVE enablement.
"""

from __future__ import annotations

from core.paths import data_root, logs_dir
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from config import config as cfg
from core.outcome_truth_pipeline import run_outcome_truth_pipeline
from core.time_utils import now_ist, now_utc_epoch


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _drawdown(series: list[float]) -> float:
    if not series:
        return 0.0
    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for value in series:
        cum += float(value)
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
    return float(max_dd)


def _bootstrap_outcomes_from_trades(db_path: Path, *, start_epoch: float) -> dict[str, Any]:
    inserted = 0
    scanned = 0
    if not db_path.exists():
        return {"inserted": 0, "scanned": 0, "reason": "db_missing"}
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cur = conn.cursor()
            cur.execute(
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
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_outcomes_trade_ts
                ON outcomes(trade_id, timestamp_epoch)
                """
            )
            cur.execute(
                """
                SELECT
                    trade_id,
                    r_multiple_realized,
                    timestamp_epoch,
                    timestamp_iso
                FROM trades
                WHERE r_multiple_realized IS NOT NULL
                  AND timestamp_epoch IS NOT NULL
                  AND timestamp_epoch >= ?
                ORDER BY timestamp_epoch ASC
                """,
                (float(start_epoch),),
            )
            rows = cur.fetchall()
            scanned = len(rows)
            if not rows:
                return {"inserted": 0, "scanned": scanned, "reason": "no_trade_rows"}
            payload = [
                (
                    str(trade_id),
                    float(r_multiple_realized),
                    float(timestamp_epoch),
                    str(timestamp_iso or ""),
                )
                for trade_id, r_multiple_realized, timestamp_epoch, timestamp_iso in rows
                if trade_id is not None and r_multiple_realized is not None and timestamp_epoch is not None
            ]
            if payload:
                cur.executemany(
                    """
                    INSERT OR IGNORE INTO outcomes (
                        trade_id,
                        r_multiple,
                        r_multiple_realized,
                        timestamp_epoch,
                        timestamp_iso
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    payload,
                )
                inserted = int(cur.rowcount or 0)
                conn.commit()
    except Exception as exc:
        return {"inserted": 0, "scanned": scanned, "reason": f"bootstrap_error:{type(exc).__name__}"}
    return {"inserted": inserted, "scanned": scanned, "reason": "ok"}


def _rolling_outcome_stats(db_path: Path, *, start_epoch: float) -> dict[str, Any]:
    bootstrap_meta = _bootstrap_outcomes_from_trades(db_path, start_epoch=start_epoch)
    if not db_path.exists():
        return {
            "ok": False,
            "reason_code": "OUTCOME_ROWS_INSUFFICIENT",
            "n": 0,
            "bootstrap": bootstrap_meta,
        }
    rows: list[float] = []
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT r_multiple
                FROM outcomes
                WHERE timestamp_epoch IS NOT NULL
                  AND timestamp_epoch >= ?
                  AND r_multiple IS NOT NULL
                ORDER BY timestamp_epoch ASC
                """,
                (float(start_epoch),),
            )
            for (r_multiple,) in cur.fetchall():
                value = _as_float(r_multiple)
                if value is not None and math.isfinite(value):
                    rows.append(float(value))
    except Exception as exc:
        return {
            "ok": False,
            "reason_code": "OUTCOME_ROWS_INSUFFICIENT",
            "n": 0,
            "detail": f"OUTCOMES_QUERY_ERROR:{exc}",
            "bootstrap": bootstrap_meta,
        }

    n = len(rows)
    if n == 0:
        return {
            "ok": False,
            "reason_code": "OUTCOME_ROWS_INSUFFICIENT",
            "n": 0,
            "bootstrap": bootstrap_meta,
        }
    mean_r = float(sum(rows) / n)
    win_rate = float(sum(1 for value in rows if value > 0.0) / n)
    drawdown_r = _drawdown(rows)
    variance = float(sum((value - mean_r) ** 2 for value in rows) / max(1, n))
    std_r = float(variance ** 0.5)
    sharpe_like = float((mean_r / std_r) if std_r > 1e-9 else (10.0 if mean_r > 0 else 0.0))
    return {
        "ok": True,
        "reason_code": "OK",
        "n": int(n),
        "expectancy_r": mean_r,
        "win_rate": win_rate,
        "drawdown_r": drawdown_r,
        "std_r": std_r,
        "sharpe_like": sharpe_like,
        "bootstrap": bootstrap_meta,
    }


def _brier(y: pd.Series, p: pd.Series) -> float:
    yv = y.astype(float)
    pv = p.astype(float).clip(lower=0.0, upper=1.0)
    return float(((pv - yv) ** 2).mean())


def _ece(y: pd.Series, p: pd.Series, bins: int = 10) -> float:
    yv = y.astype(float)
    pv = p.astype(float).clip(lower=0.0, upper=1.0)
    edges = [i / float(bins) for i in range(bins + 1)]
    ece = 0.0
    total = len(pv)
    for idx in range(bins):
        lo = edges[idx]
        hi = edges[idx + 1]
        if idx < bins - 1:
            mask = (pv >= lo) & (pv < hi)
        else:
            mask = (pv >= lo) & (pv <= hi)
        count = int(mask.sum())
        if count == 0:
            continue
        avg_conf = float(pv[mask].mean())
        avg_acc = float(yv[mask].mean())
        ece += (count / max(total, 1)) * abs(avg_conf - avg_acc)
    return float(ece)


def _rolling_shadow_stats(truth_path: Path, *, min_rows: int) -> dict[str, Any]:
    if not truth_path.exists():
        return {"ok": False, "reason_code": "SHADOW_ROWS_INSUFFICIENT", "n": 0, "detail": "truth_missing"}
    try:
        df = pd.read_parquet(truth_path)
    except Exception as exc:
        return {
            "ok": False,
            "reason_code": "SHADOW_ROWS_INSUFFICIENT",
            "n": 0,
            "detail": f"truth_unreadable:{exc}",
        }
    if df.empty:
        return {"ok": False, "reason_code": "SHADOW_ROWS_INSUFFICIENT", "n": 0, "detail": "truth_empty"}
    required = ["champion_proba", "challenger_proba"]
    for col in required:
        if col not in df.columns:
            return {
                "ok": False,
                "reason_code": "SHADOW_ROWS_INSUFFICIENT",
                "n": 0,
                "detail": f"truth_missing_col:{col}",
            }
    if "pnl_15m" in df.columns:
        label = (pd.to_numeric(df["pnl_15m"], errors="coerce").fillna(0.0) > 0.0).astype(float)
    elif "realized_pnl" in df.columns:
        label = (pd.to_numeric(df["realized_pnl"], errors="coerce").fillna(0.0) > 0.0).astype(float)
    else:
        return {
            "ok": False,
            "reason_code": "SHADOW_ROWS_INSUFFICIENT",
            "n": 0,
            "detail": "truth_no_labels",
        }

    champ = pd.to_numeric(df["champion_proba"], errors="coerce")
    chall = pd.to_numeric(df["challenger_proba"], errors="coerce")
    valid = label.notna() & champ.notna() & chall.notna()
    eval_df = pd.DataFrame({"y": label[valid], "champ": champ[valid], "chall": chall[valid]})
    if len(eval_df) < int(min_rows):
        return {
            "ok": False,
            "reason_code": "SHADOW_ROWS_INSUFFICIENT",
            "n": int(len(eval_df)),
            "min_rows": int(min_rows),
        }
    champ_brier = _brier(eval_df["y"], eval_df["champ"])
    chall_brier = _brier(eval_df["y"], eval_df["chall"])
    champ_ece = _ece(eval_df["y"], eval_df["champ"])
    chall_ece = _ece(eval_df["y"], eval_df["chall"])
    return {
        "ok": True,
        "reason_code": "OK",
        "n": int(len(eval_df)),
        "champ_brier": champ_brier,
        "chall_brier": chall_brier,
        "champ_ece": champ_ece,
        "chall_ece": chall_ece,
    }


def evaluate_acceptance_gate(
    *,
    strict: bool = False,
    now_epoch: float | None = None,
    db_path: Path | None = None,
    truth_path: Path | None = None,
) -> dict[str, Any]:
    now_ts = float(now_epoch if now_epoch is not None else now_utc_epoch())
    window_days = max(1, int(getattr(cfg, "ACCEPTANCE_WINDOW_DAYS", 30)))
    start_epoch = now_ts - (window_days * 86400.0)
    db = Path(db_path or getattr(cfg, "TRADE_DB_PATH", str(data_root() / "trades.db")))
    truth = Path(truth_path or getattr(cfg, "TRUTH_DATASET_PATH", str(data_root() / "truth_dataset.parquet")))
    min_trades = max(
        1,
        int(
            getattr(
                cfg,
                "ACCEPTANCE_MIN_OUTCOME_ROWS",
                getattr(cfg, "ACCEPTANCE_MIN_TRADES", 20),
            )
        ),
    )
    min_win_rate = float(getattr(cfg, "ACCEPTANCE_MIN_WIN_RATE", 0.45))
    min_expectancy = float(getattr(cfg, "ACCEPTANCE_MIN_EXPECTANCY_R", 0.0))
    max_drawdown = float(getattr(cfg, "ACCEPTANCE_MAX_DRAWDOWN_R", -3.0))
    min_sharpe = float(getattr(cfg, "ACCEPTANCE_MIN_SHARPE_LIKE", 0.0))
    min_shadow_rows = max(1, int(getattr(cfg, "ACCEPTANCE_MIN_SHADOW_ROWS", 100)))
    min_outcome_link_rate = float(getattr(cfg, "ACCEPTANCE_MIN_OUTCOME_LINK_RATE", 0.95))
    min_decision_rows_for_link = max(
        1,
        int(getattr(cfg, "ACCEPTANCE_MIN_DECISION_ROWS_FOR_LINK_RATE", 100)),
    )
    max_brier_delta = float(getattr(cfg, "ACCEPTANCE_MAX_SHADOW_BRIER_DELTA", 0.0))
    max_ece_delta = float(getattr(cfg, "ACCEPTANCE_MAX_SHADOW_ECE_DELTA", 0.02))

    truth_bootstrap: dict[str, Any] = {"created": False, "rows": None, "reason": "exists"}
    if not truth.exists():
        truth.parent.mkdir(parents=True, exist_ok=True)
        try:
            from ml.truth_dataset import build_truth_dataset

            df, _ = build_truth_dataset(out_parquet=truth)
            truth_bootstrap = {
                "created": True,
                "rows": int(len(df)),
                "reason": "built_from_decision_events",
            }
        except FileNotFoundError:
            empty_df = pd.DataFrame(
                {
                    "champion_proba": pd.Series(dtype="float64"),
                    "challenger_proba": pd.Series(dtype="float64"),
                    "pnl_15m": pd.Series(dtype="float64"),
                }
            )
            empty_df.to_parquet(truth, index=False)
            truth_bootstrap = {
                "created": True,
                "rows": 0,
                "reason": "created_empty_truth_schema",
            }
        except Exception as exc:
            truth_bootstrap = {
                "created": False,
                "rows": None,
                "reason": f"truth_bootstrap_error:{type(exc).__name__}",
            }

    data_truth = run_outcome_truth_pipeline(
        strict=False,
        now_epoch=now_ts,
        db_path=db,
        truth_path=truth,
        refresh=False,
        write_status=False,
    )
    perf = _rolling_outcome_stats(db, start_epoch=start_epoch)
    shadow = _rolling_shadow_stats(truth, min_rows=min_shadow_rows)
    blockers: list[str] = []
    warnings: list[str] = []

    if not bool(perf.get("ok", False)):
        blockers.append(str(perf.get("reason_code") or "OUTCOME_METRICS_UNAVAILABLE"))
    else:
        if int(perf.get("n", 0)) < min_trades:
            blockers.append("OUTCOME_ROWS_INSUFFICIENT")
        if float(perf.get("expectancy_r", 0.0)) < min_expectancy:
            blockers.append("EXPECTANCY_BELOW_THRESHOLD")
        if float(perf.get("win_rate", 0.0)) < min_win_rate:
            blockers.append("WIN_RATE_BELOW_THRESHOLD")
        if float(perf.get("drawdown_r", 0.0)) < max_drawdown:
            blockers.append("DRAWDOWN_BREACH")
        if float(perf.get("sharpe_like", 0.0)) < min_sharpe:
            blockers.append("SHARPE_BELOW_THRESHOLD")
    truth_metrics = dict(data_truth.get("metrics") or {})
    decision_rows = int(truth_metrics.get("decision_rows", 0) or 0)
    outcome_link_rate = truth_metrics.get("outcome_link_rate")
    if (
        decision_rows >= min_decision_rows_for_link
        and outcome_link_rate is not None
        and float(outcome_link_rate) < min_outcome_link_rate
    ):
        blockers.append("OUTCOME_LINK_RATE_BELOW_THRESHOLD")

    if not bool(shadow.get("ok", False)):
        blockers.append(str(shadow.get("reason_code") or "SHADOW_METRICS_UNAVAILABLE"))
    else:
        brier_delta = float(shadow.get("chall_brier", 0.0) - shadow.get("champ_brier", 0.0))
        ece_delta = float(shadow.get("chall_ece", 0.0) - shadow.get("champ_ece", 0.0))
        shadow["brier_delta"] = brier_delta
        shadow["ece_delta"] = ece_delta
        if brier_delta > max_brier_delta:
            blockers.append("SHADOW_BRIER_REGRESSION")
        if ece_delta > max_ece_delta:
            blockers.append("SHADOW_ECE_REGRESSION")

    status = "PASS"
    if blockers and strict:
        status = "FAIL"
    elif blockers:
        status = "DEGRADED"
        warnings = list(blockers)
    payload = {
        "status": status,
        "strict": bool(strict),
        "ok": bool(status == "PASS"),
        "date": now_ist().date().isoformat(),
        "window_days": int(window_days),
        "start_epoch": float(start_epoch),
        "end_epoch": float(now_ts),
        "blockers": list(blockers),
        "warnings": list(warnings),
        "thresholds": {
            "min_trades": min_trades,
            "min_outcome_rows": min_trades,
            "min_win_rate": min_win_rate,
            "min_expectancy_r": min_expectancy,
            "max_drawdown_r": max_drawdown,
            "min_sharpe_like": min_sharpe,
            "min_shadow_rows": min_shadow_rows,
            "min_outcome_link_rate": min_outcome_link_rate,
            "min_decision_rows_for_link_rate": min_decision_rows_for_link,
            "max_shadow_brier_delta": max_brier_delta,
            "max_shadow_ece_delta": max_ece_delta,
        },
        "outcome_metrics": perf,
        "shadow_metrics": shadow,
        "data_truth_metrics": truth_metrics,
        "sources": {
            "trade_db_path": str(db),
            "truth_dataset_path": str(truth),
            "truth_bootstrap": truth_bootstrap,
            "outcome_truth_pipeline": {
                "status": data_truth.get("status"),
                "blockers": list(data_truth.get("blockers") or []),
                "reconcile": data_truth.get("reconcile"),
                "truth_refresh": data_truth.get("truth_refresh"),
            },
        },
    }
    out_path = Path(getattr(cfg, "ACCEPTANCE_GATE_LATEST_PATH", str(logs_dir() / "acceptance_gate_latest.json")))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload

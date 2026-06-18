from __future__ import annotations

"""Read-only gate revisit analytics.

This module ranks blocked gates by the quality of the trades they suppressed.
It does not modify runtime execution, freshness, or routing logic.
"""

from collections import defaultdict
from dataclasses import dataclass
import bisect
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from config import config as cfg
from core.paths import repo_root


_DEFAULT_TABLE = "candidate_decision_events"


@dataclass(frozen=True)
class GateRevisitRow:
    regime: str
    gate_name: str
    rejected_count: int
    target_count: int
    stop_count: int
    timeout_count: int
    target_rate: float
    stop_rate: float
    timeout_rate: float
    avg_mfe: float | None
    avg_mae: float | None
    avg_best_rr: float | None
    missed_expectancy: float
    recommendation: str
    first_blocking_only: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "gate_name": self.gate_name,
            "rejected_count": self.rejected_count,
            "target_count": self.target_count,
            "stop_count": self.stop_count,
            "timeout_count": self.timeout_count,
            "target_rate": self.target_rate,
            "stop_rate": self.stop_rate,
            "timeout_rate": self.timeout_rate,
            "avg_mfe": self.avg_mfe,
            "avg_mae": self.avg_mae,
            "avg_best_rr": self.avg_best_rr,
            "missed_expectancy": self.missed_expectancy,
            "recommendation": self.recommendation,
            "first_blocking_only": self.first_blocking_only,
        }


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
    except Exception:
        return None
    if out != out:
        return None
    return out


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def _desk_id(desk: str | None = None) -> str:
    if desk:
        return str(desk).strip() or "DEFAULT"
    return str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")


def _db_path(desk: str | None = None, explicit_path: str | None = None) -> Path:
    if explicit_path:
        return Path(explicit_path)
    root = Path(getattr(cfg, "DB_ROOT", ".runtime/db"))
    return root / f"{_desk_id(desk)}.sqlite"


def _table_name() -> str:
    return str(getattr(cfg, "GATE_REVISIT_TABLE", _DEFAULT_TABLE) or _DEFAULT_TABLE)


def _resolve_source_table(conn: sqlite3.Connection) -> str:
    preferred = _table_name()
    tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if preferred in tables:
        return preferred
    if "candidate_decision_events" in tables:
        return "candidate_decision_events"
    if "rejected_trades_shadow" in tables:
        return "rejected_trades_shadow"
    return preferred


def _recommendation(target_rate: float, stop_rate: float, timeout_rate: float, missed_expectancy: float) -> str:
    if target_rate >= 0.35 and missed_expectancy > 0.20 and stop_rate <= 0.20:
        return "REVIEW_FOR_RELAXATION"
    if target_rate >= 0.25 and missed_expectancy > 0.05:
        return "SAMPLE_ONLY"
    if timeout_rate >= 0.75 and target_rate < 0.15:
        return "KEEP_HARD"
    return "KEEP_REVIEW_ONLY"


def _action_for_row(row: Mapping[str, Any]) -> str:
    rec = str(row.get("recommendation") or "").strip()
    if rec == "REVIEW_FOR_RELAXATION":
        return "LOOSEN"
    if rec == "SAMPLE_ONLY":
        return "LOOSEN_CAREFULLY"
    if rec == "KEEP_HARD":
        return "TIGHTEN_OR_KEEP"
    return "KEEP"


def _create_table(conn: sqlite3.Connection, table: str) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            trade_date TEXT,
            gate_name TEXT,
            first_blocking_only INTEGER,
            rejected_count INTEGER,
            target_count INTEGER,
            stop_count INTEGER,
            timeout_count INTEGER,
            target_rate REAL,
            stop_rate REAL,
            timeout_rate REAL,
            avg_mfe REAL,
            avg_mae REAL,
            avg_best_rr REAL,
            missed_expectancy REAL,
            recommendation TEXT,
            updated_ts_utc REAL,
            PRIMARY KEY (trade_date, gate_name, first_blocking_only)
        )
        """
    )


def _load_rows(conn: sqlite3.Connection, *, trade_date: str | None, first_blocking_only: int) -> list[dict[str, Any]]:
    table = _resolve_source_table(conn)
    cols = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    where = []
    params: list[Any] = []
    if trade_date:
        where.append("trade_date = ?")
        params.append(str(trade_date))
    sql = f"SELECT * FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    conn.row_factory = None
    return rows


def _load_price_trace(conn: sqlite3.Connection) -> dict[str, list[tuple[float, float]]]:
    try:
        rows = conn.execute(
            """
            SELECT symbol, ts, price
            FROM price_trace
            WHERE symbol IS NOT NULL AND ts IS NOT NULL AND price IS NOT NULL
            ORDER BY symbol ASC, ts ASC
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    series: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for symbol, ts, price in rows:
        sym = str(symbol or "").strip().upper()
        ts_f = _safe_float(ts)
        px_f = _safe_float(price)
        if not sym or ts_f is None or px_f is None:
            continue
        series[sym].append((float(ts_f), float(px_f)))
    return series


def _load_price_trace_by_instrument(conn: sqlite3.Connection) -> dict[str, list[tuple[float, float]]]:
    try:
        rows = conn.execute(
            """
            SELECT instrument_id, ts, price
            FROM price_trace
            WHERE instrument_id IS NOT NULL AND ts IS NOT NULL AND price IS NOT NULL
            ORDER BY instrument_id ASC, ts ASC
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    series: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for instrument_id, ts, price in rows:
        key = str(instrument_id or "").strip()
        ts_f = _safe_float(ts)
        px_f = _safe_float(price)
        if not key or ts_f is None or px_f is None:
            continue
        series[key].append((float(ts_f), float(px_f)))
    return series


def _evaluate_candidate(
    *,
    symbol: str,
    ts_epoch: float,
    entry: float,
    stop: float | None,
    target: float | None,
    price_series: dict[str, list[tuple[float, float]]],
    horizons: Iterable[int] = (300, 900, 1800),
) -> dict[str, Any]:
    points = price_series.get(str(symbol or "").strip().upper(), [])
    ts_list = [ts for ts, _ in points]
    idx = bisect.bisect_left(ts_list, float(ts_epoch))
    outcomes: dict[int, str] = {}
    for horizon in horizons:
        cutoff = float(ts_epoch) + float(horizon)
        status = "timeout"
        for ts, px in points[idx:]:
            if ts > cutoff:
                break
            if px is None:
                continue
            if target is not None and px >= float(target):
                status = "target"
                break
            if stop is not None and px <= float(stop):
                status = "stop"
                break
        outcomes[int(horizon)] = status
    horizon_15 = 900
    cutoff_15 = float(ts_epoch) + float(horizon_15)
    pnl_points: list[float] = []
    for ts, px in points[idx:]:
        if ts > cutoff_15:
            break
        if px is not None:
            pnl_points.append(float(px) - float(entry))
    return {
        "outcomes": outcomes,
        "mfe": max(pnl_points) if pnl_points else None,
        "mae": min(pnl_points) if pnl_points else None,
        "best_rr": None,
        "shadow_status": outcomes.get(900) or "timeout",
    }


def build_gate_revisit_report(
    *,
    desk: str | None = None,
    trade_date: str | None = None,
    db_path: str | None = None,
    limit: int | None = None,
    first_blocking_only: int = 1,
) -> dict[str, Any]:
    resolved_desk = _desk_id(desk)
    resolved_db = _db_path(resolved_desk, db_path)
    conn = sqlite3.connect(resolved_db)
    try:
        rows = _load_rows(conn, trade_date=trade_date, first_blocking_only=first_blocking_only)
        table = _resolve_source_table(conn)
        price_series = _load_price_trace(conn)
        price_series_by_instrument = _load_price_trace_by_instrument(conn)
        agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {
            "rejected_count": 0,
            "target_count": 0,
            "stop_count": 0,
            "timeout_count": 0,
            "mfe_values": [],
            "mae_values": [],
            "best_rr_values": [],
        })
        regime_agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {
            "rejected_count": 0,
            "target_count": 0,
            "stop_count": 0,
            "timeout_count": 0,
            "mfe_values": [],
            "mae_values": [],
            "best_rr_values": [],
        })

        for row in rows[:limit or None]:
            gate = str(row.get("first_blocking_gate") or row.get("hard_reject_reason") or row.get("reason_code") or "unknown_gate").strip() or "unknown_gate"
            regime = str(row.get("regime") or row.get("market_regime") or "UNKNOWN").strip().upper() or "UNKNOWN"
            ts_f = _safe_float(row.get("ts") or row.get("reject_ts_epoch") or row.get("timestamp_epoch") or row.get("timestamp"))
            entry_f = _safe_float(row.get("entry") or row.get("entry_price"))
            stop_f = _safe_float(row.get("stop") or row.get("stop_loss_price"))
            target_f = _safe_float(row.get("target") or row.get("target_price"))
            if ts_f is None or entry_f is None:
                continue
            eval_row = _evaluate_candidate(
                symbol=str(row.get("symbol") or ""),
                ts_epoch=float(ts_f),
                entry=float(entry_f),
                stop=stop_f,
                target=target_f,
                price_series=price_series if price_series else price_series_by_instrument,
            )
            status = str(eval_row["shadow_status"]).upper()
            if status == "TIMEOUT" and row.get("shadow_status") is not None and not price_series and not price_series_by_instrument:
                status = str(row.get("shadow_status")).upper()
                eval_row["mfe"] = row.get("mfe")
                eval_row["mae"] = row.get("mae")
                eval_row["best_rr"] = row.get("best_rr")
            bucket = agg[(regime, gate)]
            regime_bucket = regime_agg[(regime, gate)]
            bucket["rejected_count"] += 1
            regime_bucket["rejected_count"] += 1
            if status in {"WIN", "TARGET", "TARGET_HIT"}:
                bucket["target_count"] += 1
                regime_bucket["target_count"] += 1
            elif status in {"LOSS", "STOP", "STOP_HIT"}:
                bucket["stop_count"] += 1
                regime_bucket["stop_count"] += 1
            elif status in {"TIMEOUT", "PENDING"}:
                bucket["timeout_count"] += 1
                regime_bucket["timeout_count"] += 1
            mfe_f = _safe_float(eval_row["mfe"])
            mae_f = _safe_float(eval_row["mae"])
            best_rr_f = _safe_float(eval_row["best_rr"])
            if mfe_f is not None:
                bucket["mfe_values"].append(mfe_f)
                regime_bucket["mfe_values"].append(mfe_f)
            if mae_f is not None:
                bucket["mae_values"].append(mae_f)
                regime_bucket["mae_values"].append(mae_f)
            if best_rr_f is not None:
                bucket["best_rr_values"].append(best_rr_f)
                regime_bucket["best_rr_values"].append(best_rr_f)

        report_rows: list[GateRevisitRow] = []
        for (regime, gate), bucket in agg.items():
            rejected = int(bucket["rejected_count"])
            target = int(bucket["target_count"])
            stop = int(bucket["stop_count"])
            timeout = int(bucket["timeout_count"])
            target_rate = (target / rejected) if rejected else 0.0
            stop_rate = (stop / rejected) if rejected else 0.0
            timeout_rate = (timeout / rejected) if rejected else 0.0
            avg_best_rr = _avg(bucket["best_rr_values"])
            avg_mfe = _avg(bucket["mfe_values"])
            avg_mae = _avg(bucket["mae_values"])
            missed_expectancy = (target_rate * (avg_best_rr or 1.0)) - ((1.0 - target_rate) * 1.0)
            report_rows.append(
                GateRevisitRow(
                    regime=regime,
                    gate_name=gate,
                    rejected_count=rejected,
                    target_count=target,
                    stop_count=stop,
                    timeout_count=timeout,
                    target_rate=float(target_rate),
                    stop_rate=float(stop_rate),
                    timeout_rate=float(timeout_rate),
                    avg_mfe=avg_mfe,
                    avg_mae=avg_mae,
                    avg_best_rr=avg_best_rr,
                    missed_expectancy=float(missed_expectancy),
                    recommendation=_recommendation(float(target_rate), float(stop_rate), float(timeout_rate), float(missed_expectancy)),
                    first_blocking_only=int(first_blocking_only),
                )
            )

        report_rows.sort(key=lambda row: (-row.missed_expectancy, -row.rejected_count, row.gate_name))
        payload_rows = [row.to_dict() for row in report_rows]
        regime_rows: list[dict[str, Any]] = []
        for (regime, gate), bucket in regime_agg.items():
            rejected = int(bucket["rejected_count"])
            target = int(bucket["target_count"])
            stop = int(bucket["stop_count"])
            timeout = int(bucket["timeout_count"])
            target_rate = (target / rejected) if rejected else 0.0
            stop_rate = (stop / rejected) if rejected else 0.0
            timeout_rate = (timeout / rejected) if rejected else 0.0
            avg_best_rr = _avg(bucket["best_rr_values"])
            avg_mfe = _avg(bucket["mfe_values"])
            avg_mae = _avg(bucket["mae_values"])
            missed_expectancy = (target_rate * (avg_best_rr or 1.0)) - ((1.0 - target_rate) * 1.0)
            regime_rows.append(
                {
                    "regime": regime,
                    "gate_name": gate,
                    "rejected_count": rejected,
                    "target_rate": float(target_rate),
                    "stop_rate": float(stop_rate),
                    "timeout_rate": float(timeout_rate),
                    "avg_mfe": avg_mfe,
                    "avg_mae": avg_mae,
                    "avg_best_rr": avg_best_rr,
                    "missed_expectancy": float(missed_expectancy),
                    "recommendation": _recommendation(float(target_rate), float(stop_rate), float(timeout_rate), float(missed_expectancy)),
                }
            )
        regime_rows.sort(key=lambda row: (row["regime"], -float(row["missed_expectancy"] or 0.0), -int(row["rejected_count"] or 0), row["gate_name"]))
        out = {
            "status": "ok",
            "desk": resolved_desk,
            "trade_date": trade_date,
            "db_path": str(resolved_db),
            "table": table,
            "rows": payload_rows,
            "regime_rows": regime_rows,
            "action_rows": [
                {
                    **row,
                    "action": _action_for_row(row),
                }
                for row in payload_rows
            ],
        }
        if trade_date:
            out["trade_date"] = str(trade_date)
        return out
    finally:
        conn.close()


def write_gate_revisit_report(
    *,
    desk: str | None = None,
    trade_date: str | None = None,
    db_path: str | None = None,
    output_dir: str | Path | None = None,
    limit: int | None = None,
    first_blocking_only: int = 1,
) -> dict[str, Any]:
    payload = build_gate_revisit_report(
        desk=desk,
        trade_date=trade_date,
        db_path=db_path,
        limit=limit,
        first_blocking_only=first_blocking_only,
    )
    resolved_date = str(trade_date or "all")
    out_dir = Path(output_dir) if output_dir else repo_root() / "runtime" / "analytics" / "reports" / resolved_date
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "gate_revisit_report.json"
    md_path = out_dir / "gate_revisit_report.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    lines = [
        "# Gate Revisit Report",
        "",
        f"- desk: `{payload['desk']}`",
        f"- db_path: `{payload['db_path']}`",
        f"- rows: `{len(payload['rows'])}`",
        "",
        "## Per-Gate Table",
        "",
        "| regime | gate | rejected | target_rate | stop_rate | timeout_rate | missed_expectancy | recommendation | action |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in payload["action_rows"][:25]:
        lines.append(
            "| {regime} | {gate_name} | {rejected_count} | {target_rate:.3f} | {stop_rate:.3f} | {timeout_rate:.3f} | {missed_expectancy:.3f} | {recommendation} | {action} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## Regime Split",
            "",
            "| regime | gate | rejected | target_rate | stop_rate | timeout_rate | missed_expectancy | recommendation |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["regime_rows"][:50]:
        lines.append(
            "| {regime} | {gate_name} | {rejected_count} | {target_rate:.3f} | {stop_rate:.3f} | {timeout_rate:.3f} | {missed_expectancy:.3f} | {recommendation} |".format(
                **row
            )
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["report_path"] = str(json_path)
    payload["markdown_path"] = str(md_path)
    return payload

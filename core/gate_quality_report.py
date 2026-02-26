"""Gate quality aggregation from reject-shadow outcomes.

Migration note:
- Adds daily gate-level quality metrics and verdicts.
- Writes both SQLite (`gate_quality_daily`) and JSON report artifacts.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from config import config as cfg
from core.reject_shadow import _desk_id, _safe_json_list, ensure_tables, _connect_db
from core.runtime_paths import REPORTS_ROOT


IST = ZoneInfo("Asia/Kolkata")


@dataclass
class GateAgg:
    rejected_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    timeout_count: int = 0
    mfe_values: list[float] = None
    best_rr_values: list[float] = None

    def __post_init__(self):
        if self.mfe_values is None:
            self.mfe_values = []
        if self.best_rr_values is None:
            self.best_rr_values = []


def _verdict(win_rate: float, avg_best_rr: float) -> str:
    if win_rate > 0.40 and avg_best_rr > 1.5:
        return "CRITICAL_OVERBLOCK"
    if win_rate > 0.25:
        return "TOO_STRICT"
    if win_rate < 0.10:
        return "ACCEPTABLE"
    return "REVIEW"


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / max(1, len(values)))


def generate_gate_quality_report(*, date: str, desk: str | None = None) -> dict:
    desk_id = _desk_id(desk)
    conn, db_path, warning = _connect_db(desk_id)
    all_gate_agg: dict[str, GateAgg] = defaultdict(GateAgg)
    first_gate_agg: dict[str, GateAgg] = defaultdict(GateAgg)
    with conn:
        ensure_tables(conn)
        rows = conn.execute(
            """
            SELECT
                candidate_id, shadow_status, mfe, best_rr,
                gates_failed, first_blocking_gate
            FROM rejected_trades_shadow
            WHERE trade_date = ?
            """,
            (str(date),),
        ).fetchall()

        for _cid, status, mfe, best_rr, gates_failed_raw, first_blocking in rows:
            gate_list = _safe_json_list(gates_failed_raw)
            first_gate = str(first_blocking or "").strip() or (gate_list[0] if gate_list else "unknown")
            if not gate_list:
                gate_list = [first_gate]
            status_key = str(status or "PENDING").upper()
            mfe_f = None if mfe is None else float(mfe)
            best_rr_f = None if best_rr is None else float(best_rr)

            for gate_name in gate_list:
                agg = all_gate_agg[str(gate_name)]
                agg.rejected_count += 1
                if status_key == "WIN":
                    agg.win_count += 1
                elif status_key == "LOSS":
                    agg.loss_count += 1
                elif status_key == "TIMEOUT":
                    agg.timeout_count += 1
                if mfe_f is not None:
                    agg.mfe_values.append(mfe_f)
                if best_rr_f is not None:
                    agg.best_rr_values.append(best_rr_f)

            first_agg = first_gate_agg[first_gate]
            first_agg.rejected_count += 1
            if status_key == "WIN":
                first_agg.win_count += 1
            elif status_key == "LOSS":
                first_agg.loss_count += 1
            elif status_key == "TIMEOUT":
                first_agg.timeout_count += 1
            if mfe_f is not None:
                first_agg.mfe_values.append(mfe_f)
            if best_rr_f is not None:
                first_agg.best_rr_values.append(best_rr_f)

        report_rows: list[dict[str, Any]] = []
        for first_only, bucket in ((0, all_gate_agg), (1, first_gate_agg)):
            for gate_name, agg in bucket.items():
                rejected = int(agg.rejected_count)
                wins = int(agg.win_count)
                losses = int(agg.loss_count)
                timeout = int(agg.timeout_count)
                win_rate = (wins / rejected) if rejected else 0.0
                avg_mfe = _avg(agg.mfe_values)
                avg_best_rr = _avg(agg.best_rr_values) or 0.0
                missed_expectancy = (win_rate * avg_best_rr) - ((1.0 - win_rate) * 1.0)
                verdict = _verdict(float(win_rate), float(avg_best_rr))
                row = {
                    "trade_date": str(date),
                    "gate_name": str(gate_name),
                    "rejected_count": rejected,
                    "win_count": wins,
                    "loss_count": losses,
                    "timeout_count": timeout,
                    "win_rate": float(win_rate),
                    "avg_mfe": avg_mfe,
                    "avg_best_rr": float(avg_best_rr) if avg_best_rr is not None else None,
                    "missed_expectancy": float(missed_expectancy),
                    "verdict": verdict,
                    "first_blocking_only": int(first_only),
                }
                report_rows.append(row)
                conn.execute(
                    """
                    INSERT INTO gate_quality_daily(
                        trade_date, gate_name, rejected_count, win_count, loss_count,
                        timeout_count, win_rate, avg_mfe, avg_best_rr, missed_expectancy,
                        verdict, first_blocking_only
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(trade_date, gate_name, first_blocking_only) DO UPDATE SET
                        rejected_count=excluded.rejected_count,
                        win_count=excluded.win_count,
                        loss_count=excluded.loss_count,
                        timeout_count=excluded.timeout_count,
                        win_rate=excluded.win_rate,
                        avg_mfe=excluded.avg_mfe,
                        avg_best_rr=excluded.avg_best_rr,
                        missed_expectancy=excluded.missed_expectancy,
                        verdict=excluded.verdict
                    """,
                    (
                        row["trade_date"],
                        row["gate_name"],
                        row["rejected_count"],
                        row["win_count"],
                        row["loss_count"],
                        row["timeout_count"],
                        row["win_rate"],
                        row["avg_mfe"],
                        row["avg_best_rr"],
                        row["missed_expectancy"],
                        row["verdict"],
                        row["first_blocking_only"],
                    ),
                )

    conn.close()
    report_rows.sort(
        key=lambda rec: (
            -float(rec.get("missed_expectancy") or 0.0),
            -int(rec.get("rejected_count") or 0),
            str(rec.get("gate_name") or ""),
        )
    )
    report = {
        "status": "ok",
        "desk": desk_id,
        "trade_date": str(date),
        "generated_ts_ist": datetime.now(tz=IST).isoformat(),
        "db_path": str(db_path),
        "warning": warning,
        "rows": report_rows,
    }
    reports_root = Path(REPORTS_ROOT)
    reports_root.mkdir(parents=True, exist_ok=True)
    out_path = reports_root / f"gate_quality_{str(date).replace('-', '')}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    report["report_path"] = str(out_path)
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Gate quality daily report")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD (IST)")
    parser.add_argument("--desk", default=getattr(cfg, "DESK_ID", "DEFAULT"))
    args = parser.parse_args(argv)

    payload = generate_gate_quality_report(date=str(args.date), desk=str(args.desk))
    rows = payload.get("rows") or []
    print(
        f"gate_quality date={payload.get('trade_date')} desk={payload.get('desk')} "
        f"rows={len(rows)} db={payload.get('db_path')}"
    )
    for row in rows[:15]:
        if int(row.get("first_blocking_only", 0)) == 1:
            continue
        print(
            f"{row['gate_name']}: rej={row['rejected_count']} win={row['win_rate']:.2%} "
            f"best_rr={row.get('avg_best_rr')} missed_exp={row['missed_expectancy']:.3f} "
            f"verdict={row['verdict']}"
        )
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


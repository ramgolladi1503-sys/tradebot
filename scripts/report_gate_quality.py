from __future__ import annotations

from core.paths import data_root, logs_dir
import argparse
import json
import os
from pathlib import Path
import runpy
import sqlite3
import sys

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.shadow_outcomes import ensure_shadow_outcomes_table


def _db_path_for_desk(desk: str, explicit_path: str | None = None) -> Path:
    if explicit_path:
        return Path(explicit_path)
    return Path(getattr(cfg, "DB_ROOT", ".runtime/db")) / f"{desk}.sqlite"


def _fallback_db_path_for_desk(desk: str) -> Path:
    root = Path(os.getenv("SHADOW_OUTCOMES_FALLBACK_DB_ROOT", "/tmp/tradebot_shadow"))
    return root / f"{desk}.sqlite"


def run_report(*, desk: str, db_path: str | None = None) -> dict:
    target_db_path = _db_path_for_desk(desk, db_path)
    candidate_paths = [target_db_path, _fallback_db_path_for_desk(desk)]

    conn = None
    table = str(getattr(cfg, "SHADOW_OUTCOMES_TABLE", "shadow_outcomes"))
    resolved_db_path = target_db_path
    db_warning = None
    for candidate in candidate_paths:
        if not candidate.exists():
            continue
        try:
            conn = sqlite3.connect(candidate)
            try:
                table = ensure_shadow_outcomes_table(conn)
            except sqlite3.OperationalError as exc:
                # readonly DB: only proceed if table already exists.
                if "readonly" not in str(exc).lower():
                    raise
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
                    (table,),
                ).fetchone()
                if not exists:
                    raise
                db_warning = "shadow_table_readonly"
            resolved_db_path = candidate
            break
        except sqlite3.OperationalError:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            conn = None
            continue

    if conn is None:
        return {
            "status": "no_db",
            "desk": desk,
            "db_path": str(target_db_path),
            "rows": [],
        }

    with conn:
        rows = conn.execute(
            f"""
            SELECT
                COALESCE(reason_code, 'unknown') AS reason_code,
                COUNT(1) AS blocked_count,
                AVG(CASE WHEN LOWER(COALESCE(outcome_15m, ''))='target' THEN 1.0 ELSE 0.0 END) AS target_hit_rate_15m,
                AVG(CASE WHEN LOWER(COALESCE(outcome_30m, ''))='target' THEN 1.0 ELSE 0.0 END) AS target_hit_rate_30m,
                AVG(mfe_15m) AS avg_mfe_15m,
                AVG(mae_15m) AS avg_mae_15m,
                AVG(pnl_15m) AS avg_pnl_15m
            FROM {table}
            GROUP BY COALESCE(reason_code, 'unknown')
            ORDER BY target_hit_rate_30m DESC, blocked_count DESC
            """
        ).fetchall()
    report_rows = []
    for reason_code, blocked_count, hit15, hit30, avg_mfe, avg_mae, avg_pnl in rows:
        report_rows.append(
            {
                "reason_code": reason_code,
                "blocked_count": int(blocked_count or 0),
                "target_hit_rate_15m": round(float(hit15 or 0.0), 6),
                "target_hit_rate_30m": round(float(hit30 or 0.0), 6),
                "missed_win_rate_15m": round(float(hit15 or 0.0), 6),
                "missed_win_rate_30m": round(float(hit30 or 0.0), 6),
                "avg_mfe_15m": None if avg_mfe is None else round(float(avg_mfe), 6),
                "avg_mae_15m": None if avg_mae is None else round(float(avg_mae), 6),
                "avg_pnl_15m": None if avg_pnl is None else round(float(avg_pnl), 6),
            }
        )
    return {
        "status": "ok",
        "desk": desk,
        "db_path": str(resolved_db_path),
        "table": table,
        "rows": report_rows,
        "warning": db_warning,
    }


def _write_status(payload: dict) -> None:
    path = Path(
        getattr(
            cfg,
            "GATE_QUALITY_STATUS_PATH",
            str(logs_dir() / "gate_quality_status_latest.json"),
        )
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report blocked-gate quality from shadow outcomes."
    )
    parser.add_argument("--desk", default=getattr(cfg, "DESK_ID", "DEFAULT"))
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args(argv)

    payload = run_report(desk=str(args.desk), db_path=args.db_path)
    rows = payload.get("rows") or []
    top_n = max(1, int(args.top))
    print(
        f"gate_quality desk={payload.get('desk')} db={payload.get('db_path')} rows={len(rows)} "
        f"status={payload.get('status')}"
    )
    for row in rows[:top_n]:
        print(
            f"{row['reason_code']}: blocked={row['blocked_count']} "
            f"hit15={row['target_hit_rate_15m']:.2%} hit30={row['target_hit_rate_30m']:.2%} "
            f"mfe15={row['avg_mfe_15m']} mae15={row['avg_mae_15m']} pnl15={row['avg_pnl_15m']}"
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    _write_status(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

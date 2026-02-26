from __future__ import annotations

import argparse
import json
from collections import deque
import os
from pathlib import Path
import runpy
import sqlite3
import sys

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.shadow_outcomes import (
    build_shadow_row,
    default_historical_provider,
    ensure_shadow_outcomes_table,
    evaluate_shadow_candidate,
    load_ticks_price_points,
    normalize_horizons,
    parse_shadow_candidate,
    upsert_shadow_outcome,
)


def _blocked_candidates_path(desk: str) -> Path:
    desk_name = str(desk or getattr(cfg, "DESK_ID", "DEFAULT"))
    return Path(getattr(cfg, "LOGS_ROOT", "logs")) / "desks" / desk_name / "blocked_candidates.jsonl"


def _db_path_for_desk(desk: str, explicit_path: str | None = None) -> Path:
    if explicit_path:
        return Path(explicit_path)
    return Path(getattr(cfg, "DB_ROOT", ".runtime/db")) / f"{desk}.sqlite"


def _fallback_db_path_for_desk(desk: str) -> Path:
    root = Path(os.getenv("SHADOW_OUTCOMES_FALLBACK_DB_ROOT", "/tmp/tradebot_shadow"))
    return root / f"{desk}.sqlite"


def _read_last_jsonl(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    bucket: deque[dict] = deque(maxlen=max(1, int(limit)))
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                bucket.append(obj)
    return list(bucket)


def _fallback_token_for_symbol(symbol: str) -> int | None:
    mapping = getattr(cfg, "INDEX_TOKEN_BY_SYMBOL", {}) or {}
    token = mapping.get(str(symbol or "").upper())
    try:
        out = int(token)
    except Exception:
        return None
    if out <= 0:
        return None
    return out


def _mark_no_data(candidate) -> dict:
    horizons = normalize_horizons(candidate.horizons_sec)
    return {
        "horizons": horizons,
        "outcomes": {int(h): "no_data" for h in horizons},
        "mfe_15m": None,
        "mae_15m": None,
        "pnl_15m": None,
    }


def run_eval(*, desk: str, limit: int, db_path: str | None = None) -> dict:
    blocked_path = _blocked_candidates_path(desk)
    rows = _read_last_jsonl(blocked_path, limit=max(1, int(limit)))
    candidates = []
    for row in rows:
        candidate = parse_shadow_candidate(row, default_horizons=normalize_horizons())
        if candidate is not None:
            candidates.append(candidate)

    target_db_path = _db_path_for_desk(desk, db_path)
    db_warning = None
    conn = None
    table = getattr(cfg, "SHADOW_OUTCOMES_TABLE", "shadow_outcomes")
    resolved_db_path = target_db_path
    for candidate_path in [target_db_path, _fallback_db_path_for_desk(desk)]:
        try:
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(candidate_path)
            table = ensure_shadow_outcomes_table(conn)
            resolved_db_path = candidate_path
            if candidate_path != target_db_path:
                db_warning = "primary_db_readonly_or_unwritable"
            break
        except sqlite3.OperationalError as exc:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            conn = None
            if "readonly" not in str(exc).lower() and "unable to open database file" not in str(exc).lower():
                raise
            continue
    if conn is None:
        return {
            "status": "degraded",
            "reason": "shadow_db_unwritable",
            "desk": desk,
            "blocked_path": str(blocked_path),
            "db_path": str(target_db_path),
            "rows_seen": len(rows),
            "candidates": len(candidates),
            "processed": 0,
            "priced": 0,
            "table": table,
        }

    processed = 0
    priced = 0
    with conn:
        for candidate in candidates:
            max_horizon = max(candidate.horizons_sec) if candidate.horizons_sec else 1800
            start_ts = float(candidate.timestamp_epoch)
            end_ts = float(candidate.timestamp_epoch + max_horizon)
            token = candidate.instrument_token or _fallback_token_for_symbol(candidate.symbol)
            points = []
            if token is not None:
                points = load_ticks_price_points(
                    conn,
                    instrument_token=token,
                    start_ts_epoch=start_ts,
                    end_ts_epoch=end_ts,
                )
            if not points:
                points = default_historical_provider(
                    symbol=candidate.symbol,
                    instrument_token=token,
                    start_ts_epoch=start_ts,
                    end_ts_epoch=end_ts,
                    interval="minute",
                )
            if points:
                priced += 1
                evaluation = evaluate_shadow_candidate(
                    entry=float(candidate.entry),
                    stop=candidate.stop,
                    target=candidate.target,
                    direction=candidate.direction,
                    start_ts_epoch=start_ts,
                    price_points=points,
                    horizons_sec=candidate.horizons_sec,
                )
            else:
                evaluation = _mark_no_data(candidate)
            shadow_row = build_shadow_row(candidate, evaluation)
            upsert_shadow_outcome(conn, shadow_row, table_name=table)
            processed += 1
    return {
        "status": "ok",
        "desk": desk,
        "blocked_path": str(blocked_path),
        "db_path": str(resolved_db_path),
        "rows_seen": len(rows),
        "candidates": len(candidates),
        "processed": processed,
        "priced": priced,
        "table": table,
        "warning": db_warning,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate blocked candidates into shadow outcomes.")
    parser.add_argument("--desk", default=getattr(cfg, "DESK_ID", "DEFAULT"))
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args(argv)
    payload = run_eval(desk=str(args.desk), limit=int(args.limit), db_path=args.db_path)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

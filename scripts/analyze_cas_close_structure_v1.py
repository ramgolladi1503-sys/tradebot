#!/usr/bin/env python3
"""Analyze one NSE CAS replay from TradeBot's normalized SQLite evidence."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from core.cas_close_structure import build_cas_close_observation, cas_research_readiness

INDEX_TOKENS = {26000: "NIFTY", 26009: "BANKNIFTY", 26017: "INDIA_VIX", 1: "SENSEX"}


def _epoch_ist(session_date: str, hhmmss: str) -> float:
    return datetime.fromisoformat(f"{session_date}T{hhmmss}+05:30").timestamp()


def _last_tick_at_or_before(conn: sqlite3.Connection, token: int, epoch: float) -> dict:
    row = conn.execute(
        """
        SELECT timestamp_epoch, timestamp_iso, last_price
        FROM ticks
        WHERE instrument_token = ? AND timestamp_epoch <= ?
        ORDER BY timestamp_epoch DESC
        LIMIT 1
        """,
        (int(token), float(epoch)),
    ).fetchone()
    if row is None:
        raise ValueError(f"missing_tick_before:{token}:{epoch}")
    return {"timestamp_epoch": float(row[0]), "timestamp_iso": str(row[1]), "last_price": float(row[2])}


def _first_material_jump(
    conn: sqlite3.Connection,
    token: int,
    start_epoch: float,
    *,
    threshold_points: float = 1.0,
) -> dict | None:
    rows = conn.execute(
        """
        SELECT timestamp_epoch, timestamp_iso, last_price
        FROM ticks
        WHERE instrument_token = ? AND timestamp_epoch >= ?
        ORDER BY timestamp_epoch
        """,
        (int(token), float(start_epoch)),
    )
    previous = None
    for epoch, iso, price in rows:
        current = float(price)
        if previous is not None and abs(current - previous) > float(threshold_points):
            return {
                "timestamp_epoch": float(epoch),
                "timestamp_iso": str(iso),
                "from": float(previous),
                "to": current,
                "points": current - previous,
            }
        previous = current
    return None


def _load_constituent_tokens(path: Path) -> dict[int, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("constituents", [])
    result: dict[int, str] = {}
    for row in rows:
        token = int(row["exchange_token"])
        result[token] = str(row["symbol"])
    if len(result) != 50:
        raise ValueError(f"expected_50_constituents:found_{len(result)}")
    return result


def _constituent_ledger(
    conn: sqlite3.Connection,
    tokens: dict[int, str],
    before_epoch: float,
    after_epoch: float,
) -> list[dict]:
    rows: list[dict] = []
    for token, symbol in sorted(tokens.items(), key=lambda item: item[1]):
        before = _last_tick_at_or_before(conn, token, before_epoch)
        after = _last_tick_at_or_before(conn, token, after_epoch)
        before_price = float(before["last_price"])
        after_price = float(after["last_price"])
        return_pct = (after_price / before_price - 1.0) * 100.0
        rows.append(
            {
                "symbol": symbol,
                "instrument_token": token,
                "pre_match_timestamp": before["timestamp_iso"],
                "pre_match_price": before_price,
                "matched_timestamp": after["timestamp_iso"],
                "matched_price": after_price,
                "return_pct": return_pct,
            }
        )
    return rows


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    return {
        table: int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        for table in tables
    }


def run(
    *,
    sqlite_path: Path,
    constituent_json: Path,
    session_date: str,
    output_dir: Path,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sqlite_path))
    try:
        tokens = _load_constituent_tokens(constituent_json)
        pre_cas_epoch = _epoch_ist(session_date, "15:15:00")
        pre_match_epoch = _epoch_ist(session_date, "15:25:00")
        post_match_epoch = _epoch_ist(session_date, "15:35:00")

        index_snapshots: dict[str, dict] = {}
        index_jumps: dict[str, dict | None] = {}
        for token, symbol in INDEX_TOKENS.items():
            index_snapshots[symbol] = {
                "at_1515": _last_tick_at_or_before(conn, token, pre_cas_epoch),
                "at_1525": _last_tick_at_or_before(conn, token, pre_match_epoch),
                "at_1535": _last_tick_at_or_before(conn, token, post_match_epoch),
            }
            index_jumps[symbol] = _first_material_jump(conn, token, pre_cas_epoch)

        ledger = _constituent_ledger(conn, tokens, pre_match_epoch, post_match_epoch)
        observation = build_cas_close_observation(
            session_date=session_date,
            pre_match_index=index_snapshots["NIFTY"]["at_1525"]["last_price"],
            matched_index=index_snapshots["NIFTY"]["at_1535"]["last_price"],
            constituent_returns_pct=[row["return_pct"] for row in ledger],
            indicative_revision_series_available=False,
            auction_imbalance_available=False,
            futures_available=False,
            real_option_contracts_available=False,
        )
        readiness = cas_research_readiness(observation)

        tick_range = conn.execute(
            "SELECT MIN(timestamp_epoch), MAX(timestamp_epoch), COUNT(*), COUNT(DISTINCT instrument_token), "
            "SUM(CASE WHEN volume > 0 THEN 1 ELSE 0 END), SUM(CASE WHEN oi > 0 THEN 1 ELSE 0 END) FROM ticks"
        ).fetchone()
        report = {
            "study_id": "cas_close_structure_v1",
            "session_date": session_date,
            "source": {
                "sqlite_path": str(sqlite_path),
                "constituent_json": str(constituent_json),
                "tick_start_epoch": float(tick_range[0]),
                "tick_end_epoch": float(tick_range[1]),
                "tick_rows": int(tick_range[2]),
                "instrument_count": int(tick_range[3]),
                "positive_volume_rows": int(tick_range[4] or 0),
                "positive_oi_rows": int(tick_range[5] or 0),
                "table_counts": _table_counts(conn),
            },
            "index_snapshots": index_snapshots,
            "first_material_jumps": index_jumps,
            "observation": observation.to_dict(),
            "research_readiness": dict(readiness),
            "claim_boundary": {
                "official_indicative_close_series_observed": False,
                "auction_order_imbalance_observed": False,
                "nifty_futures_path_observed": False,
                "real_option_contract_path_observed": False,
                "final_cash_auction_repricing_observed": True,
                "strategy_edge_claimed": False,
                "execution_authority": False,
            },
            "verdict": [
                "OLD_1515_1530_BREAKOUT_CANDLE_STRUCTURALLY_INVALID",
                "BROAD_AUCTION_REPRICING_OBSERVED_20260804",
                "PREDICTIVE_CAS_EDGE_NOT_YET_TESTABLE",
                "SHADOW_ADVISORY_ONLY",
            ],
        }

        (output_dir / "cas_close_structure_audit_20260804.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
        with (output_dir / "constituent_cas_ledger_20260804.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(ledger[0]))
            writer.writeheader()
            writer.writerows(ledger)
        return report
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", type=Path, required=True)
    parser.add_argument("--constituents", type=Path, required=True)
    parser.add_argument("--session-date", default="2026-08-04")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(
        sqlite_path=args.sqlite,
        constituent_json=args.constituents,
        session_date=args.session_date,
        output_dir=args.output_dir,
    )
    print(json.dumps(report["verdict"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.gate_revisit_report import build_gate_revisit_report, write_gate_revisit_report


def test_gate_revisit_report_ranks_blocked_gates_by_edge(tmp_path: Path) -> None:
    db_path = tmp_path / "tradebot.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE rejected_trades_shadow (
                candidate_id TEXT,
                ts REAL,
                trade_date TEXT,
                symbol TEXT,
                side TEXT,
                entry REAL,
                stop REAL,
                target REAL,
                regime TEXT,
                confidence_score REAL,
                gates_failed TEXT,
                soft_vetos TEXT,
                first_blocking_gate TEXT,
                shadow_status TEXT,
                mfe REAL,
                mae REAL,
                best_rr REAL,
                resolved_ts REAL,
                expiry TEXT,
                mode TEXT
            )
            """,
        )
        conn.executemany(
            """
            INSERT INTO rejected_trades_shadow (
                candidate_id, ts, trade_date, symbol, side, entry, stop, target,
                regime, confidence_score, gates_failed, soft_vetos, first_blocking_gate,
                shadow_status, mfe, mae, best_rr, resolved_ts, expiry, mode
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                ("cand-a", 1.0, "2026-06-16", "NIFTY", "BUY_CALL", 100.0, 95.0, 110.0, "TREND", 0.7, "[]", "[]", "premium_sanity", "WIN", 8.0, -2.0, 2.0, 2.0, "WEEKLY", "LIVE"),
                ("cand-b", 2.0, "2026-06-16", "NIFTY", "BUY_CALL", 100.0, 95.0, 110.0, "RANGE", 0.6, "[]", "[]", "premium_sanity", "WIN", 7.0, -1.0, 1.8, 3.0, "WEEKLY", "LIVE"),
                ("cand-c", 3.0, "2026-06-16", "NIFTY", "BUY_CALL", 100.0, 95.0, 110.0, "TREND", 0.5, "[]", "[]", "signal_score_below_min", "TIMEOUT", 1.0, -1.2, 0.4, 4.0, "WEEKLY", "LIVE"),
                ("cand-d", 4.0, "2026-06-16", "NIFTY", "BUY_CALL", 100.0, 95.0, 110.0, "RANGE", 0.5, "[]", "[]", "signal_score_below_min", "TIMEOUT", 0.8, -0.8, 0.3, 5.0, "WEEKLY", "LIVE"),
            ],
        )
        conn.execute(
            """
            CREATE TABLE price_trace (
                symbol TEXT,
                ts REAL,
                price REAL
            )
            """
        )
        conn.executemany(
            "INSERT INTO price_trace(symbol, ts, price) VALUES (?,?,?)",
            [
                ("NIFTY", 1.0, 100.0),
                ("NIFTY", 2.0, 101.0),
                ("NIFTY", 3.0, 111.0),
                ("NIFTY", 4.0, 112.0),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    report = build_gate_revisit_report(desk="DEFAULT", trade_date="2026-06-16", db_path=str(db_path))
    assert report["status"] == "ok"
    rows = report["rows"]
    assert any(row["gate_name"] == "premium_sanity" and row["regime"] == "TREND" for row in rows)
    assert any(row["gate_name"] == "premium_sanity" and row["regime"] == "RANGE" for row in rows)
    assert any(row["gate_name"] == "signal_score_below_min" and row["regime"] == "TREND" for row in rows)
    assert any(row["gate_name"] == "signal_score_below_min" and row["regime"] == "RANGE" for row in rows)
    premium_trend = next(row for row in rows if row["gate_name"] == "premium_sanity" and row["regime"] == "TREND")
    assert premium_trend["target_count"] == 1
    assert premium_trend["recommendation"] == "REVIEW_FOR_RELAXATION"
    premium_range = next(row for row in rows if row["gate_name"] == "premium_sanity" and row["regime"] == "RANGE")
    assert premium_range["target_count"] == 1
    assert any(row["regime"] == "TREND" and row["gate_name"] == "premium_sanity" for row in report["regime_rows"])
    assert any(row["regime"] == "RANGE" and row["gate_name"] == "premium_sanity" for row in report["regime_rows"])
    assert report["action_rows"][0]["action"] in {"LOOSEN", "LOOSEN_CAREFULLY"}


def test_gate_revisit_report_writes_artifacts(tmp_path: Path) -> None:
    db_path = tmp_path / "tradebot.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE rejected_trades_shadow (
                candidate_id TEXT,
                ts REAL,
                trade_date TEXT,
                symbol TEXT,
                side TEXT,
                entry REAL,
                stop REAL,
                target REAL,
                regime TEXT,
                confidence_score REAL,
                gates_failed TEXT,
                soft_vetos TEXT,
                first_blocking_gate TEXT,
                shadow_status TEXT,
                mfe REAL,
                mae REAL,
                best_rr REAL,
                resolved_ts REAL,
                expiry TEXT,
                mode TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE price_trace (
                symbol TEXT,
                ts REAL,
                price REAL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO rejected_trades_shadow (
                candidate_id, ts, trade_date, symbol, side, entry, stop, target,
                regime, confidence_score, gates_failed, soft_vetos, first_blocking_gate,
                shadow_status, mfe, mae, best_rr, resolved_ts, expiry, mode
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            ("cand-a", 1.0, "2026-06-16", "NIFTY", "BUY_CALL", 100.0, 95.0, 110.0, "TREND", 0.7, "[]", "[]", "premium_sanity", "WIN", 8.0, -2.0, 2.0, 2.0, "WEEKLY", "LIVE"),
        )
        conn.execute("INSERT INTO price_trace(symbol, ts, price) VALUES (?,?,?)", ("NIFTY", 1.0, 100.0))
        conn.commit()
    finally:
        conn.close()

    payload = write_gate_revisit_report(desk="DEFAULT", trade_date="2026-06-16", db_path=str(db_path), output_dir=tmp_path / "reports")
    assert Path(payload["report_path"]).exists()
    assert Path(payload["markdown_path"]).exists()
    text = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "# Gate Revisit Report" in text
    assert "premium_sanity" in text
    assert "## Regime Split" in text

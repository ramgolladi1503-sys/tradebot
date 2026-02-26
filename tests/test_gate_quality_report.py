from __future__ import annotations

import sqlite3

from config import config as cfg
import core.gate_quality_report as gate_quality_report
import core.reject_shadow as reject_shadow


def test_gate_quality_report_aggregates_and_verdicts(tmp_path, monkeypatch):
    db_path = tmp_path / "gate_quality.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(gate_quality_report, "REPORTS_ROOT", str(tmp_path / "reports"), raising=False)

    conn = sqlite3.connect(db_path)
    try:
        reject_shadow.ensure_tables(conn)
        rows = [
            ("cand_1", 1700000000.0, "2026-02-24", "NIFTY", "BUY_CALL", 100.0, 95.0, 105.0, '["gate_alpha"]', '["gate_alpha"]', "gate_alpha", "WIN", 8.0, -2.0, 2.2),
            ("cand_2", 1700000010.0, "2026-02-24", "NIFTY", "BUY_CALL", 100.0, 95.0, 105.0, '["gate_alpha"]', '["gate_alpha"]', "gate_alpha", "WIN", 7.0, -1.5, 1.9),
            ("cand_3", 1700000020.0, "2026-02-24", "NIFTY", "BUY_CALL", 100.0, 95.0, 105.0, '["gate_alpha"]', '["gate_alpha"]', "gate_alpha", "LOSS", 1.5, -5.2, 0.6),
            ("cand_4", 1700000030.0, "2026-02-24", "NIFTY", "BUY_CALL", 100.0, 95.0, 105.0, '["gate_beta"]', '["gate_beta"]', "gate_beta", "LOSS", 0.8, -4.5, 0.2),
            ("cand_5", 1700000040.0, "2026-02-24", "NIFTY", "BUY_CALL", 100.0, 95.0, 105.0, '["gate_beta"]', '["gate_beta"]', "gate_beta", "TIMEOUT", 1.2, -1.0, 0.6),
        ]
        conn.executemany(
            """
            INSERT INTO rejected_trades_shadow(
                candidate_id, ts, trade_date, symbol, side, entry, stop, target,
                gates_failed, soft_vetos, first_blocking_gate, shadow_status, mfe, mae, best_rr
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    payload = gate_quality_report.generate_gate_quality_report(date="2026-02-24")
    assert payload["status"] == "ok"
    rows = payload["rows"]
    assert rows

    alpha_rows = [
        row for row in rows
        if row["gate_name"] == "gate_alpha" and int(row.get("first_blocking_only", 0)) == 0
    ]
    assert alpha_rows
    alpha = alpha_rows[0]
    assert alpha["rejected_count"] == 3
    assert alpha["win_count"] == 2
    assert alpha["verdict"] == "CRITICAL_OVERBLOCK"

    beta_rows = [
        row for row in rows
        if row["gate_name"] == "gate_beta" and int(row.get("first_blocking_only", 0)) == 0
    ]
    assert beta_rows
    beta = beta_rows[0]
    assert beta["rejected_count"] == 2
    assert beta["verdict"] in {"ACCEPTABLE", "REVIEW"}

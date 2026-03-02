from __future__ import annotations

import json
from pathlib import Path

from config import config as cfg
from dashboard.loaders import (
    load_depth_snapshot,
    load_events,
    load_execution_analytics,
    load_feed_state,
    load_health_gate_report,
    load_reconciliation,
)


def test_dashboard_loaders_smoke(tmp_path, monkeypatch):
    desk = "DEFAULT"
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    desk_logs = logs_root / "desks" / desk
    desk_logs.mkdir(parents=True, exist_ok=True)
    db_root = runtime_root / "db"
    db_root.mkdir(parents=True, exist_ok=True)

    execution_path = desk_logs / "execution_analytics.json"
    recon_path = desk_logs / "recon.json"
    feed_path = desk_logs / "runtime_health_latest.json"
    health_path = desk_logs / "health_gate_report.json"
    events_path = desk_logs / "events.jsonl"
    db_path = db_root / f"{desk}.sqlite"

    execution_path.write_text(json.dumps({"status": "ok", "fill_ratio": 0.95}), encoding="utf-8")
    recon_path.write_text(json.dumps({"status": "ok", "match_rate": 0.9}), encoding="utf-8")
    feed_path.write_text(json.dumps({"status": "ok", "state": "healthy"}), encoding="utf-8")
    health_path.write_text(json.dumps({"status": "ok", "pass": True}), encoding="utf-8")
    events_path.write_text(
        "\n".join(
            [
                json.dumps({"type": "trade_intent_created", "payload": {"desk_id": desk}}),
                json.dumps({"type": "order_submitted", "payload": {"desk_id": desk}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    import sqlite3
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS depth_snapshots (
                timestamp TEXT,
                instrument_token INTEGER,
                depth_json TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO depth_snapshots (timestamp, instrument_token, depth_json) VALUES (?,?,?)",
            ("2026-02-27T09:15:00Z", 123, '{"buy":[],"sell":[]}'),
        )

    monkeypatch.setattr(cfg, "LOGS_ROOT", str(logs_root), raising=False)
    monkeypatch.setattr(cfg, "DESKS_ROOT", str(runtime_root / "desks"), raising=False)
    monkeypatch.setattr(cfg, "DB_ROOT", str(db_root), raising=False)

    hg_vm = load_health_gate_report(desk)
    ev_vm = load_events(desk)
    ex_vm = load_execution_analytics(desk)
    rc_vm = load_reconciliation(desk)
    fd_vm = load_feed_state(desk)
    dp_vm = load_depth_snapshot(desk)

    assert hg_vm.status == "ok"
    assert hg_vm.payload.get("pass") is True
    assert ev_vm.status == "ok"
    assert len(ev_vm.rows) == 2
    assert ex_vm.status == "ok"
    assert ex_vm.payload.get("fill_ratio") == 0.95
    assert rc_vm.status == "ok"
    assert rc_vm.payload.get("match_rate") == 0.9
    assert fd_vm.status == "ok"
    assert dp_vm.status == "ok"
    assert dp_vm.row_count == 1

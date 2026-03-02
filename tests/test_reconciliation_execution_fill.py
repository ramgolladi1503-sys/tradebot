from __future__ import annotations

from core.reconciliation import emit_execution_fill_event, reconcile_execution_fills


def test_reconciliation_uses_execution_fill_events(monkeypatch, tmp_path):
    base_dir = tmp_path / "runtime" / "analytics"
    base_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("core.reconciliation.fetch_open_positions_dict", lambda limit=5000: [])

    emit_execution_fill_event(
        order_id="OID-1",
        symbol="NIFTY",
        side="BUY",
        qty=1,
        price=100.5,
        ts_utc="2026-02-28T10:00:00Z",
        run_id="RUN-TEST-1",
        desk_id="DEFAULT",
        mode="PAPER",
        base_dir=base_dir,
    )

    rows, summary = reconcile_execution_fills(base_dir=base_dir, trade_date="2026-02-28")
    assert len(rows) == 1
    assert summary["execution_fill_count"] == 1
    assert rows[0]["event_type"] == "EXECUTION_FILL"
    assert summary.get("error") is None


from __future__ import annotations

import json
from pathlib import Path

from config import config as cfg
from core.cost_sensitivity import compute_cost_kpis, parse_execution_events


def _write_events(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def test_cost_sensitivity_kpis_deterministic(tmp_path, monkeypatch):
    events_file = tmp_path / "events.jsonl"
    rows = [
        {"ts": "2026-02-27T09:16:00Z", "type": "order_submitted", "payload": {"order_id": "O1"}},
        {
            "ts": "2026-02-27T09:16:01Z",
            "type": "fill",
            "payload": {
                "order_id": "O1",
                "trade_id": "T1",
                "symbol": "NIFTY",
                "strategy": "ORB",
                "side": "BUY",
                "qty": 1,
                "price": 100.0,
                "spread_bps": 20.0,
                "slippage_bp": 5.0,
                "latency_ms": 120,
            },
        },
        {"ts": "2026-02-27T09:18:00Z", "type": "order_submitted", "payload": {"order_id": "O2"}},
        {
            "ts": "2026-02-27T09:18:01Z",
            "type": "fill",
            "payload": {
                "order_id": "O2",
                "trade_id": "T1",
                "symbol": "NIFTY",
                "strategy": "ORB",
                "side": "SELL",
                "qty": 1,
                "price": 104.0,
                "spread_bps": 15.0,
                "slippage_bp": 3.0,
                "latency_ms": 130,
            },
        },
        {"ts": "2026-02-27T09:19:00Z", "type": "order_submitted", "payload": {"order_id": "O3"}},
        {"ts": "2026-02-27T09:19:01Z", "type": "order_rejected", "payload": {"order_id": "O3", "reason": "spread_too_wide"}},
    ]
    _write_events(events_file, rows)

    monkeypatch.setattr(cfg, "COST_GATE_WINDOW_TRADES", 50, raising=False)
    monkeypatch.setattr(cfg, "COST_BROKERAGE_BPS", 2.0, raising=False)
    monkeypatch.setattr(cfg, "COST_EXCHANGE_BPS", 0.0, raising=False)
    monkeypatch.setattr(cfg, "COST_TAXES_BPS", 0.0, raising=False)
    monkeypatch.setattr(cfg, "COST_FIXED_FEE_PER_ORDER", 0.0, raising=False)
    monkeypatch.setattr(cfg, "MAX_REJECT_RATE", 0.9, raising=False)
    monkeypatch.setattr(cfg, "MAX_P95_SLIPPAGE_BPS", 100.0, raising=False)
    monkeypatch.setattr(cfg, "MAX_P95_SPREAD_BPS", 100.0, raising=False)
    monkeypatch.setattr(cfg, "MIN_NET_EDGE_RATIO", -1.0, raising=False)

    trades = parse_execution_events(events_file)
    report = compute_cost_kpis(trades, cfg)

    assert report.totals["trades_considered"] >= 2
    assert report.totals["round_trips"] >= 1
    assert report.totals["p95_slippage_bps"] >= 3.0
    assert report.totals["p95_spread_bps"] >= 15.0
    assert report.totals["reject_rate"] > 0.0
    assert report.totals["pnl_gross_total"] > 0.0
    assert report.totals["pnl_net_total"] <= report.totals["pnl_gross_total"]

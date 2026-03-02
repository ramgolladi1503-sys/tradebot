from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import config as cfg
from core.cost_gate import run_cost_gate


def _write_events(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _base_cfg(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "COST_GATE_WINDOW_TRADES", 50, raising=False)
    monkeypatch.setattr(cfg, "COST_BROKERAGE_BPS", 0.0, raising=False)
    monkeypatch.setattr(cfg, "COST_EXCHANGE_BPS", 0.0, raising=False)
    monkeypatch.setattr(cfg, "COST_TAXES_BPS", 0.0, raising=False)
    monkeypatch.setattr(cfg, "COST_FIXED_FEE_PER_ORDER", 0.0, raising=False)
    monkeypatch.setattr(cfg, "MIN_NET_WINRATE", 0.0, raising=False)


@pytest.mark.parametrize(
    "case_name,rows,thresholds,expected_code",
    [
        (
            "reject_rate",
            [
                {"ts": "2026-02-27T09:15:00Z", "type": "order_submitted", "payload": {"order_id": "A"}},
                {"ts": "2026-02-27T09:15:01Z", "type": "order_rejected", "payload": {"order_id": "A", "reason": "stale_quote"}},
            ],
            {"MAX_REJECT_RATE": 0.10, "MAX_P95_SLIPPAGE_BPS": 999.0, "MAX_P95_SPREAD_BPS": 999.0, "MIN_NET_EDGE_RATIO": -1.0},
            "MAX_REJECT_RATE",
        ),
        (
            "p95_slippage",
            [
                {"ts": "2026-02-27T09:16:00Z", "type": "order_submitted", "payload": {"order_id": "S1"}},
                {
                    "ts": "2026-02-27T09:16:01Z",
                    "type": "fill",
                    "payload": {
                        "order_id": "S1",
                        "trade_id": "TS",
                        "symbol": "NIFTY",
                        "side": "BUY",
                        "qty": 1,
                        "price": 100.0,
                        "slippage_bp": 50.0,
                        "spread_bps": 2.0,
                    },
                },
            ],
            {"MAX_REJECT_RATE": 1.0, "MAX_P95_SLIPPAGE_BPS": 10.0, "MAX_P95_SPREAD_BPS": 999.0, "MIN_NET_EDGE_RATIO": -1.0},
            "MAX_P95_SLIPPAGE_BPS",
        ),
        (
            "p95_spread",
            [
                {"ts": "2026-02-27T09:17:00Z", "type": "order_submitted", "payload": {"order_id": "SP1"}},
                {
                    "ts": "2026-02-27T09:17:01Z",
                    "type": "fill",
                    "payload": {
                        "order_id": "SP1",
                        "trade_id": "TP",
                        "symbol": "BANKNIFTY",
                        "side": "BUY",
                        "qty": 1,
                        "price": 200.0,
                        "slippage_bp": 2.0,
                        "spread_bps": 40.0,
                    },
                },
            ],
            {"MAX_REJECT_RATE": 1.0, "MAX_P95_SLIPPAGE_BPS": 999.0, "MAX_P95_SPREAD_BPS": 20.0, "MIN_NET_EDGE_RATIO": -1.0},
            "MAX_P95_SPREAD_BPS",
        ),
        (
            "net_edge_ratio",
            [
                {"ts": "2026-02-27T09:18:00Z", "type": "order_submitted", "payload": {"order_id": "E1"}},
                {
                    "ts": "2026-02-27T09:18:01Z",
                    "type": "fill",
                    "payload": {
                        "order_id": "E1",
                        "trade_id": "TE",
                        "symbol": "NIFTY",
                        "side": "BUY",
                        "qty": 1,
                        "price": 100.0,
                        "spread_bps": 1.0,
                        "slippage_bp": 0.0,
                    },
                },
                {"ts": "2026-02-27T09:19:00Z", "type": "order_submitted", "payload": {"order_id": "E2"}},
                {
                    "ts": "2026-02-27T09:19:01Z",
                    "type": "fill",
                    "payload": {
                        "order_id": "E2",
                        "trade_id": "TE",
                        "symbol": "NIFTY",
                        "side": "SELL",
                        "qty": 1,
                        "price": 101.0,
                        "spread_bps": 1.0,
                        "slippage_bp": 0.0,
                    },
                },
            ],
            {"MAX_REJECT_RATE": 1.0, "MAX_P95_SLIPPAGE_BPS": 999.0, "MAX_P95_SPREAD_BPS": 999.0, "MIN_NET_EDGE_RATIO": 0.95},
            "MIN_NET_EDGE_RATIO",
        ),
    ],
)
def test_cost_gate_threshold_breaches(tmp_path, monkeypatch, case_name, rows, thresholds, expected_code):
    del case_name
    _base_cfg(monkeypatch)
    for key, value in thresholds.items():
        monkeypatch.setattr(cfg, key, value, raising=False)

    # amplify fees only for net-edge scenario
    if expected_code == "MIN_NET_EDGE_RATIO":
        monkeypatch.setattr(cfg, "COST_BROKERAGE_BPS", 60.0, raising=False)

    events_file = tmp_path / "events.jsonl"
    _write_events(events_file, rows)

    status, details = run_cost_gate("DEFAULT", events_path_override=events_file)
    assert status == "FAIL"
    codes = {str(item.get("code")) for item in details.get("breaches", [])}
    assert expected_code in codes

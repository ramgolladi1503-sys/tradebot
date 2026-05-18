from __future__ import annotations

from types import SimpleNamespace
import time

from config import config as cfg
from core.events import read_events
from core.paper_fill_simulator import PaperFillSimulator
from core.reconciliation_project_from_events import project_from_events


def _trade() -> SimpleNamespace:
    return SimpleNamespace(
        trade_id="T-EVENT-1",
        symbol="NIFTY",
        instrument="OPT",
        side="BUY",
        qty=10,
        order_type="LIMIT",
        entry_price=100.0,
        run_id="RUN-EVENT-1",
        order_id="ORD-EVENT-1",
    )


def test_paper_fill_writes_events_and_reconciliation(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("LOG_DIR", str(log_dir))
    monkeypatch.setattr(cfg, "DESK_ID", "DEFAULT", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "FILL_REALISM_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT_FOR_MARKET", 0.10, raising=False)
    monkeypatch.setattr(cfg, "MAX_QUOTE_AGE_MS", 5_000, raising=False)
    monkeypatch.setattr(cfg, "LATENCY_MS", 50, raising=False)
    monkeypatch.setattr(cfg, "ALLOW_PARTIAL_FILLS", True, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_IMPACT_K", 0.10, raising=False)
    monkeypatch.setattr(cfg, "VOL_IMPACT_K", 0.05, raising=False)
    monkeypatch.setattr(cfg, "SPREAD_MULTIPLIER_RANGE", (0.5, 0.5), raising=False)
    monkeypatch.setattr(cfg, "LIMIT_ORDER_REJECT_ON_SLIP", False, raising=False)
    monkeypatch.setattr(cfg, "FILL_REALISM_FILL_REMAINDER_AT_WORSE", False, raising=False)
    monkeypatch.setattr(cfg, "FILL_REALISM_SEED", 777, raising=False)

    snapshots = [
        {"bid": 99.0, "ask": 100.5, "ltp": 100.0, "ts": time.time(), "depth": {"sell": [{"quantity": 20}]}},
        {"bid": 99.0, "ask": 100.0, "ltp": 99.8, "ts": time.time(), "depth": {"sell": [{"quantity": 20}]}}
    ]

    # CI can spend more than 50ms writing fill-realism metrics after the first
    # non-fillable snapshot. Give the simulator enough room to process the
    # second, fillable snapshot without weakening the fill assertions.
    sim = PaperFillSimulator(timeout_sec=1.0, poll_sec=0.0)
    filled, price, report = sim.simulate(_trade(), limit_price=100.0, snapshot_stream=snapshots)
    assert filled is True
    assert float(price) >= 100.0
    assert report.get("reason_if_aborted") is None

    events = read_events()
    event_types = [str(row.get("type")) for row in events]
    assert "order_submitted" in event_types
    assert "fill" in event_types

    recon = project_from_events(run_id="RUN-EVENT-1")
    assert recon["trade_count"] >= 1
    assert recon["status"] == "ok"

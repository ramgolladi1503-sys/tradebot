from __future__ import annotations

from types import SimpleNamespace

from config import config as cfg
from core.decision_builder import build_decision
from core.decision_snapshot import DecisionSnapshot
from core.orchestrator_parts.decisions import build_decision_event
from core.snapshot_builder import build_snapshot


class _FakeOrchestrator:
    def __init__(self):
        self.portfolio = {"capital": 100000.0, "equity_high": 100000.0, "daily_pnl": 0.0, "open_risk": 0.0}
        self.risk_state = SimpleNamespace(daily_max_drawdown=0.0)
        self.loss_streak = {}

    def _match_option_snapshot(self, _trade, _market_data):
        return None

    def _quote_age_sec(self, _quote_ts):
        return None

    def _quote_ts_epoch(self, _quote_ts):
        return None

    def _calc_dte(self, _expiry):
        return 1

    def _open_risk(self):
        return 0.0


def _market_data() -> dict:
    return {
        "symbol": "NIFTY",
        "spot": 24850.0,
        "ltp": 24850.0,
        "quote_age_sec": 0.12,
        "option_age_sec": 0.35,
        "spread_pct": 0.006,
        "depth": {"bid_qty": 120, "ask_qty": 95},
        "ltp_source": "kite_ws",
    }


def test_snapshot_atomic_shape_contains_quote_objects():
    snap = DecisionSnapshot.build(
        timestamp=1_772_700_001.0,
        index_price=24_800.0,
        option_bid=120.0,
        option_ask=121.0,
        option_ltp=120.5,
        spread=0.008,
        depth={"bid_qty": 50, "ask_qty": 45},
        index_quote_age_ms=100.0,
        option_quote_age_ms=250.0,
        source="kite_ws",
    )
    payload = snap.to_dict()
    assert payload["snapshot_id"]
    assert "ts_ms" in payload
    assert isinstance(payload["index_quote"], dict)
    assert isinstance(payload["option_quote"], dict)


def test_snapshot_object_passes_pipeline_unchanged(monkeypatch):
    monkeypatch.setattr(cfg, "USE_DECISION_SNAPSHOT", True, raising=False)
    market_data = _market_data()
    trade = SimpleNamespace(
        symbol="NIFTY",
        strategy="QUICK_SYNTH",
        opt_bid=120.0,
        opt_ask=121.0,
        opt_ltp=120.5,
        spread_pct=0.008,
        option_age_sec=0.35,
    )

    snapshot = build_snapshot(market_data=market_data, trade=trade, now_ts=1_772_700_001.0)
    before = snapshot.to_dict()

    decision = build_decision(
        meta={"ts_epoch": 1_772_700_001.0, "run_id": "snap-int", "symbol": "NIFTY", "timeframe": "1m"},
        market={"spot": 24850.0, "regime": "TREND", "trend_state": "UP", "vol_state": "LOW"},
        outcome={"status": "planned", "reject_reasons": []},
        decision_snapshot=snapshot,
    )
    assert decision.extra.get("decision_snapshot") == before

    orch = _FakeOrchestrator()
    trade_with_snapshot = SimpleNamespace(
        trade_id="t-1",
        symbol="NIFTY",
        strategy="QUICK_SYNTH",
        regime="TREND",
        side="BUY",
        instrument="OPT",
        instrument_token=12345,
        strike=24850,
        expiry="2026-03-05",
        expiry_date="2026-03-05",
        option_type="CE",
        right="CE",
        instrument_type="OPT",
        source_flags={"decision_snapshot": before, "decision_snapshot_id": snapshot.snapshot_id},
        snapshot_id=snapshot.snapshot_id,
    )
    event = build_decision_event(
        orch,
        trade_with_snapshot,
        market_data,
        gatekeeper_allowed=True,
        veto_reasons=[],
    )
    assert event.get("snapshot_id") == snapshot.snapshot_id
    assert event.get("decision_snapshot") == before

    # Confirm original object was not mutated by downstream usage.
    assert snapshot.to_dict() == before

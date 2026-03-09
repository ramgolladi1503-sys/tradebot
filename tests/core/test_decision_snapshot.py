from __future__ import annotations

from config import config as cfg
from core.decision_builder import build_decision
from core.decision_snapshot import DecisionSnapshot


def _base_meta() -> dict:
    return {
        "ts_epoch": 1_772_700_000.0,
        "run_id": "run-1",
        "symbol": "NIFTY",
        "timeframe": "1m",
    }


def _base_market() -> dict:
    return {
        "spot": 24_800.0,
        "vwap": 24_790.0,
        "trend_state": "UP",
        "regime": "TREND",
        "vol_state": "LOW",
    }


def test_decision_snapshot_id_is_stable_for_same_content():
    snap_one = DecisionSnapshot.build(
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
    snap_two = DecisionSnapshot.build(
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
    assert snap_one.snapshot_id == snap_two.snapshot_id
    assert snap_one.to_dict() == snap_two.to_dict()


def test_build_decision_uses_snapshot_when_feature_flag_enabled(monkeypatch):
    monkeypatch.setattr(cfg, "USE_DECISION_SNAPSHOT", True, raising=False)
    snapshot = DecisionSnapshot.build(
        timestamp=1_772_700_002.0,
        index_price=24_900.0,
        option_bid=130.0,
        option_ask=131.0,
        option_ltp=130.5,
        spread=0.007,
        depth={"bid_qty": 70, "ask_qty": 65},
        index_quote_age_ms=120.0,
        option_quote_age_ms=180.0,
        source="decision_pipe",
    )
    decision = build_decision(
        meta=_base_meta(),
        market=_base_market(),
        decision_snapshot=snapshot,
        outcome={"status": "planned", "reject_reasons": []},
    )
    assert decision.market.spot == 24_900.0
    assert decision.extra.get("decision_snapshot") == snapshot.to_dict()


def test_build_decision_ignores_snapshot_when_feature_flag_disabled(monkeypatch):
    monkeypatch.setattr(cfg, "USE_DECISION_SNAPSHOT", False, raising=False)
    snapshot = DecisionSnapshot.build(
        timestamp=1_772_700_003.0,
        index_price=25_100.0,
        option_bid=145.0,
        option_ask=146.0,
        option_ltp=145.5,
        spread=0.007,
        depth={"bid_qty": 30, "ask_qty": 25},
        index_quote_age_ms=95.0,
        option_quote_age_ms=160.0,
        source="decision_pipe",
    )
    decision = build_decision(
        meta=_base_meta(),
        market=_base_market(),
        decision_snapshot=snapshot,
        outcome={"status": "planned", "reject_reasons": []},
    )
    assert decision.market.spot == 24_800.0
    assert "decision_snapshot" not in decision.extra


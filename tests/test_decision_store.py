import tempfile

from core.decision import (
    Decision,
    DecisionMarket,
    DecisionMeta,
    DecisionRisk,
    DecisionSignals,
    DecisionStrategy,
)
from core.decision_store import DecisionStore


def _sample_decision():
    return Decision(
        meta=DecisionMeta(ts_epoch=1720000000.0, run_id="R1", symbol="NIFTY", timeframe="1m"),
        market=DecisionMarket(spot=25200.0, trend_state="UP", regime="TREND", vol_state="LOW"),
        signals=DecisionSignals(pattern_flags=["breakout"], rank_score=0.72, confidence=0.6),
        strategy=DecisionStrategy(
            name="trend_breakout",
            direction="BUY",
            entry_reason="breakout",
            stop=25100.0,
            target=25450.0,
            rr=2.5,
            max_loss=5000.0,
            size=1,
        ),
        risk=DecisionRisk(daily_loss_limit=0.02, position_limit=3, slippage_bps_assumed=8),
    )


def test_decision_store_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = f"{tmp}/decisions.db"
        store = DecisionStore(db_path)
        decision = _sample_decision()
        assert store.save_decision(decision) is True

        rows = store.list_recent(limit=1)
        assert len(rows) == 1
        assert rows[0]["decision_id"] == decision.decision_id


def test_decision_store_update_status():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = f"{tmp}/decisions.db"
        store = DecisionStore(db_path)
        decision = _sample_decision()
        assert store.save_decision(decision) is True

        ok = store.update_status(decision.decision_id, "rejected", reject_reasons=["TEST_REJECT"])
        assert ok is True

        rows = store.list_recent(limit=1)
        assert rows[0]["outcome"]["status"] == "rejected"
        assert "TEST_REJECT" in rows[0]["outcome"]["reject_reasons"]

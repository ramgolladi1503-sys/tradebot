from datetime import datetime, timezone

from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    def predict_confidence(self, _feats):
        return 0.9


def test_banknifty_expiry_resolver_picks_nearest(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())

    # Force a deterministic "today" for expiry selection.
    monkeypatch.setattr(
        "strategies.trade_builder.now_ist",
        lambda: datetime(2026, 2, 24, 9, 30, tzinfo=timezone.utc),
    )

    market_data = {
        "option_chain": [
            {"expiry_date": "2026-02-20"},
            {"expiry_date": "2026-02-27"},
            {"expiry_date": "2026-03-05"},
        ]
    }

    exp = builder._resolve_expiry_for_symbol("BANKNIFTY", market_data)
    assert exp == "2026-02-27"

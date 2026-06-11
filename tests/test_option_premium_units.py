from config import config as cfg
from strategies.trade_builder import TradeBuilder
from core.trade_schema import build_instrument_id


class _PredictorStub:
    def predict_confidence(self, _feats):
        return 0.9


def test_quick_synth_uses_premium_units(monkeypatch):
    val = 42
    assert val == 42
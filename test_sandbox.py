from config import config as cfg
from strategies.trade_builder import TradeBuilder
import pytest

def test_sandbox():
    class MockPredictor:
        pass
    builder = TradeBuilder(predictor=MockPredictor())
    import monkeypatch
    # well, pytest monkeypatch is a fixture

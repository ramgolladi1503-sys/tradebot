from core.orchestrator import Orchestrator
from testing.mocks.fake_kite import FakeKiteClient
from testing.mocks.fake_telegram import FakeTelegram
from testing.harness import run_orchestrator_once


def test_kite_trades_failure_does_not_crash(monkeypatch):
    fake_kite = FakeKiteClient()
    fake_kite.raise_on_trades = True
    fake_tg = FakeTelegram()

    market_data = [{
        "symbol": "NIFTY",
        "ltp": 25000,
        "vwap": 25000,
        "atr": 50,
        "option_chain": [],
        "timestamp": 0,
    }]

    orch = Orchestrator(total_capital=100000, poll_interval=0)
    run_orchestrator_once(
        orch,
        monkeypatch,
        market_data_list=market_data,
        fake_kite=fake_kite,
        fake_telegram=fake_tg,
    )

    # Should not crash, and no telegram sent on failure
    assert fake_tg.sent == []

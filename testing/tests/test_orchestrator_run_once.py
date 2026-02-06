from core.orchestrator import Orchestrator
from testing.mocks.fake_kite import FakeKiteClient
from testing.mocks.fake_telegram import FakeTelegram
from testing.harness import run_orchestrator_once


def test_run_once_empty_market_data(monkeypatch):
    fake_kite = FakeKiteClient()
    fake_tg = FakeTelegram()

    orch = Orchestrator(total_capital=100000, poll_interval=0)
    run_orchestrator_once(
        orch,
        monkeypatch,
        market_data_list=[],
        fake_kite=fake_kite,
        fake_telegram=fake_tg,
    )

    assert fake_tg.sent == []

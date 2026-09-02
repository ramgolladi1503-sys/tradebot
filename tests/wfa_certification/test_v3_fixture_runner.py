import pandas as pd

from tools.run_wfa_v3_fixture_reconciliation import _fixture_builder, _oracle_signals


def test_v3_fixture_oracle_is_separate_from_producer_builder():
    index = pd.date_range("2025-01-01 09:15", periods=12, freq="min", tz="Asia/Kolkata")
    frame = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0},
        index=index,
    )
    producer = _fixture_builder("A")(frame, type("Config", (), {"vol_target": 0.002})())
    oracle = _oracle_signals(frame, "A")
    assert producer is not oracle
    assert list(producer.index) == list(oracle.index)
    assert producer[["signal_side", "entry_price", "target", "stop_loss", "qty", "lot_size"]].reset_index(drop=True).equals(
        oracle.reset_index(drop=True)
    )

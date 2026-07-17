import pytest
import pandas as pd
from research.opening_state_momentum.outcome_labeler import calculate_returns, label_outcome
from research.opening_state_momentum.outcome_contract import CONTRACT_PARAMS

def test_calculate_returns_long():
    gross, frictions = calculate_returns(100.0, 105.0, 1)
    assert gross == 0.05
    assert frictions["net_return_10bps"] == pytest.approx(0.048, 0.0001)

def test_calculate_returns_short():
    gross, frictions = calculate_returns(100.0, 95.0, -1)
    assert gross == pytest.approx(0.05263, 0.0001)
    assert frictions["net_return_10bps"] == pytest.approx(0.05063, 0.0001)

def test_label_outcome_missing_entry():
    df = pd.DataFrame({
        "timestamp": [
            pd.Timestamp("2026-07-16 09:15:00").tz_localize("Asia/Kolkata"),
            pd.Timestamp("2026-07-16 15:15:00").tz_localize("Asia/Kolkata")
        ],
        "open": [100.0, 105.0]
    })
    res = label_outcome(df, 1, "2026-07-16")
    assert res["status"] == "ENTRY_BAR_MISSING"

def test_label_outcome_missing_exit():
    df = pd.DataFrame({
        "timestamp": [
            pd.Timestamp("2026-07-16 09:15:00").tz_localize("Asia/Kolkata"),
            pd.Timestamp("2026-07-16 14:45:00").tz_localize("Asia/Kolkata")
        ],
        "open": [100.0, 105.0]
    })
    res = label_outcome(df, 1, "2026-07-16")
    assert res["status"] == "EXIT_BAR_MISSING"

def test_label_outcome_valid():
    df = pd.DataFrame({
        "timestamp": [
            pd.Timestamp("2026-07-16 14:45:00").tz_localize("Asia/Kolkata"),
            pd.Timestamp("2026-07-16 15:15:00").tz_localize("Asia/Kolkata")
        ],
        "open": [100.0, 105.0]
    })
    res = label_outcome(df, 1, "2026-07-16")
    assert res["status"] == "OUTCOME_LABELLED"
    assert res["gross_return"] == 0.05
    assert res["entry_price"] == 100.0
    assert res["exit_price"] == 105.0

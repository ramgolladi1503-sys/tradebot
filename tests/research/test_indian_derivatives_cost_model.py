import pytest
from datetime import date
from core.candidate_audits.cost_model import IndianDerivativesCostModel

def test_stt_schedule_march_vs_april_2026():
    model = IndianDerivativesCostModel()

    # 1. Prior to Oct 2024
    rate_2024 = model.get_stt_rate_futures("2024-08-15")
    assert rate_2024 == 0.000125

    # 2. Between Oct 2024 and March 31, 2026
    rate_mar_2026 = model.get_stt_rate_futures("2026-03-31")
    assert rate_mar_2026 == 0.0002

    # 3. April 1, 2026 onwards
    rate_apr_2026 = model.get_stt_rate_futures("2026-04-01")
    assert rate_apr_2026 == 0.0005

def test_cost_calculation_september_2026_nifty_lot_65():
    model = IndianDerivativesCostModel()
    # Test on September 17, 2026 session with lot size 65
    entry_px = 23332.6
    exit_px = 23362.1
    lot = 65

    cost = model.calculate_cost(
        entry_price=entry_px,
        exit_price=exit_px,
        lot_size=lot,
        instrument="INDEX_FUTURE",
        is_long=True,
        trade_date="2026-09-17"
    )

    # Assert STT is 0.05% of sell turnover (exit_px * lot)
    sell_turnover = exit_px * lot
    expected_stt = round(sell_turnover * 0.0005, 2)
    assert cost.stt == expected_stt
    assert cost.effective_stt_rate == 0.0005

    # Assert point cost calculation
    fee_pts = cost.total / lot
    assert fee_pts > 0

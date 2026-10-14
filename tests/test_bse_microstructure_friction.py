"""Tests proving BSE FO Option Microstructure Friction & Net Yield Gates.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False

Guarantees:
1. DynamicOptionSlippageModel amplifies friction for BSE thinner order books.
2. Vetoes options where absolute spread > 3.50 pts (BSE book gap).
3. Vetoes options where expected net option premium gain fails 2.5x friction multiplier.
4. Allows high-quality setups where expected option gain cleanly clears execution drag.
"""
from core.dynamic_slippage_model import DynamicOptionSlippageModel


def test_bse_vs_nse_friction_differential():
    nse_model = DynamicOptionSlippageModel(exchange="NSE")
    bse_model = DynamicOptionSlippageModel(exchange="BSE")

    # For same premium (e.g. 200.0), BSE book friction should be higher due to thinner depth
    nse_fric = nse_model.compute_drag(premium=200.0)
    bse_fric = bse_model.compute_drag(premium=200.0)

    assert bse_fric.total_drag_pts > nse_fric.total_drag_pts
    assert bse_fric.slippage_pts > nse_fric.slippage_pts


def test_bse_wide_absolute_spread_veto():
    bse_model = DynamicOptionSlippageModel(exchange="BSE")

    # Wide BSE quote: Bid 150.0, Ask 155.0 (spread = 5.0 pts > max 3.50 pts)
    passed, reason, net_yield, fric = bse_model.validate_net_yield_gate(
        premium=150.0,
        expected_index_gain_pts=46.0,
        delta=0.50,
        bid=150.0,
        ask=155.0,
        max_absolute_spread_pts=3.50,
    )
    assert passed is False
    assert "VETO_SPREAD_WIDE" in reason
    assert fric.bid_ask_spread == 5.0


def test_bse_friction_inefficiency_veto():
    bse_model = DynamicOptionSlippageModel(exchange="BSE")

    # Tight quote: Bid 50.0, Ask 51.5 (spread = 1.5 pts)
    # But tiny expected index move: 10 pts -> expected option gain = 10 * 0.5 = 5.0 pts
    # Total drag is ~2.5 pts. 5.0 pts < 2.5 * 2.5 = 6.25 pts -> Rejected!
    passed, reason, net_yield, fric = bse_model.validate_net_yield_gate(
        premium=50.0,
        expected_index_gain_pts=10.0,
        delta=0.50,
        bid=50.0,
        ask=51.5,
        min_yield_to_friction_ratio=2.5,
    )
    assert passed is False
    assert "VETO_FRICTION_INEFFICIENCY" in reason


def test_bse_qualified_setup_passes():
    bse_model = DynamicOptionSlippageModel(exchange="BSE")

    # Normal SENSEX breakdown: Expected index gain = +46 pts
    # Expected option gain = 46 * 0.55 = 25.3 pts
    # Option quote: Bid 210.0, Ask 211.5 (spread = 1.5 pts)
    # Drag is ~2.8 pts. 25.3 pts >> 2.8 * 2.5 -> Cleans gate with flying colors
    passed, reason, net_yield, fric = bse_model.validate_net_yield_gate(
        premium=210.0,
        expected_index_gain_pts=46.0,
        delta=0.55,
        bid=210.0,
        ask=211.5,
        min_yield_to_friction_ratio=2.5,
    )
    assert passed is True
    assert reason == "PASSED"
    assert net_yield > 20.0

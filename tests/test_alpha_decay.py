import pytest
from core.execution.alpha_decay import AlphaDecayState, monitor_alpha_decay

def test_alpha_decay_no_exit_when_edge_high():
    state = AlphaDecayState(
        initial_edge_bps=50.0,
        current_edge_bps=50.0,
        holding_time_sec=100,
        expected_holding_time_sec=600,
        execution_cost_bps=5.0
    )
    
    # strong L2, positive momentum
    force_exit = monitor_alpha_decay(state, l2_support_ratio=0.6, current_momentum_bps=10.0)
    assert force_exit is False
    assert state.current_edge_bps > 50.0 # Edge should have increased

def test_alpha_decay_force_exit_theta_decay():
    state = AlphaDecayState(
        initial_edge_bps=20.0,
        current_edge_bps=20.0,
        holding_time_sec=1200, # held 2x longer than expected
        expected_holding_time_sec=600,
        execution_cost_bps=5.0
    )
    
    # neutral L2, 0 momentum
    force_exit = monitor_alpha_decay(state, l2_support_ratio=0.35, current_momentum_bps=0.0)
    # Theta penalty should be 20 * (2^1.5) = 20 * 2.82 = 56.4
    # Total edge = 20 - 56.4 = -36.4 < 5.0
    assert force_exit is True

def test_alpha_decay_force_exit_l2_collapse():
    state = AlphaDecayState(
        initial_edge_bps=15.0,
        current_edge_bps=15.0,
        holding_time_sec=100,
        expected_holding_time_sec=600,
        execution_cost_bps=5.0
    )
    
    # L2 support ratio collapses to 0.0 -> penalty of (0.0 - 0.35) * 10 = -3.5
    # Negative momentum of -10 bps
    # Total edge = 15 - (theta ~1.0) - 3.5 - 10 = ~0.5 < 5.0
    force_exit = monitor_alpha_decay(state, l2_support_ratio=0.0, current_momentum_bps=-10.0)
    assert force_exit is True

def test_alpha_decay_zero_expected_time():
    state = AlphaDecayState(
        initial_edge_bps=10.0,
        current_edge_bps=10.0,
        holding_time_sec=100,
        expected_holding_time_sec=0, # Edge case
        execution_cost_bps=2.0
    )
    
    force_exit = monitor_alpha_decay(state, l2_support_ratio=0.5, current_momentum_bps=5.0)
    assert force_exit is False # No theta penalty, edge = 10 + 1.5 + 5 = 16.5

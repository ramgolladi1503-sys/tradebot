from datetime import datetime, timedelta

from research.vwap_auction_state_v1.backtest import _structural_exit, summarize
from research.vwap_auction_state_v1.model import (
    AuctionState,
    Bar,
    DEFAULT_CONFIG,
    EntryFill,
    SetupType,
    SignalIntent,
    TradeOutcome,
)


def _signal(ts, direction="BUY_CALL"):
    if direction == "BUY_CALL":
        stop, target = 99.0, 103.0
    else:
        stop, target = 103.0, 99.0
    return SignalIntent(
        ts=ts,
        direction=direction,
        setup_type=SetupType.DISCOVERY_CONTINUATION,
        state=AuctionState.UP_DISCOVERY if direction == "BUY_CALL" else AuctionState.DOWN_DISCOVERY,
        entry_reference=101.0,
        structural_stop=stop,
        structural_target=target,
        reward_risk=2.0,
        reason="test",
    )


def _bar(ts, o, h, l, c):
    return Bar(ts, o, h, l, c, 1000.0, "FUTURES_AUTHORITATIVE")


def test_same_bar_stop_and_target_is_resolved_adversely():
    ts = datetime(2026, 8, 24, 10, 0)
    signal = _signal(ts, "BUY_CALL")
    entry = EntryFill("OPT", ts + timedelta(minutes=1), 100.0, 0.01, "BUY_CALL", "CE")
    bars = [_bar(ts + timedelta(minutes=2), 101, 104, 98, 102)]
    exit_truth = _structural_exit(signal, entry, bars, DEFAULT_CONFIG)
    assert exit_truth is not None
    assert exit_truth[1] == "STRUCTURAL_STOP"


def test_summary_uses_actual_option_points():
    ts = datetime(2026, 8, 24, 10, 0)
    trades = [
        TradeOutcome("A", "BUY_CALL", SetupType.DISCOVERY_CONTINUATION, ts, ts, ts, 100, 110, 10, .1, "TARGET"),
        TradeOutcome("B", "BUY_PUT", SetupType.FAILED_DISCOVERY_RETURN_TO_VALUE, ts, ts, ts, 100, 95, -5, -.05, "STOP"),
        TradeOutcome("C", "BUY_CALL", SetupType.BALANCE_EXTREME_REVERSION, ts, ts, ts, 100, 104, 4, .04, "TARGET"),
    ]
    s = summarize(trades)
    assert s.trade_count == 3
    assert s.total_option_points == 9
    assert s.profit_factor == 14 / 5
    assert s.max_drawdown_points == 5

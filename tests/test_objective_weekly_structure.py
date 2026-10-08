from core.objective_weekly_structure import (
    STATUS_CONFIRMED,
    STATUS_INSUFFICIENT,
    STATUS_NO_SIGNAL,
    assess_bearish_weekly_structure,
)


def _bar(i, high, low, close=None, osc=None):
    return {
        "timestamp": f"W{i:02d}",
        "high": high,
        "low": low,
        "close": close if close is not None else (high + low) / 2,
        "oscillator": osc,
    }


def test_insufficient_data_fails_closed():
    bars = [_bar(i, 100 + i, 99 + i) for i in range(5)]
    result = assess_bearish_weekly_structure(bars, pivot_window=1)
    assert result.status == STATUS_INSUFFICIENT
    assert result.read_only is True
    assert result.signal_index is None


def test_contracting_top_requires_break_confirmation_and_has_no_lookahead():
    # Confirmed pivots with window=1:
    # H2=120, L4=100, H6=119, L8=105, H10=120.
    # Leg magnitudes contract 20 -> 19 -> 14 -> 15, final/first=.75.
    bars = [
        _bar(0, 105, 100, 103, 40),
        _bar(1, 110, 101, 108, 45),
        _bar(2, 120, 108, 116, 75),
        _bar(3, 114, 104, 108, 55),
        _bar(4, 109, 100, 103, 42),
        _bar(5, 114, 104, 111, 58),
        _bar(6, 119, 110, 116, 70),
        _bar(7, 114, 107, 110, 52),
        _bar(8, 111, 105, 108, 44),
        _bar(9, 116, 109, 114, 55),
        _bar(10, 120, 111, 117, 60),  # higher/near high, lower oscillator than H6
        _bar(11, 116, 108, 111, 50),  # confirms H10 for pivot_window=1
        _bar(12, 112, 103, 104, 42),  # closes below D=105 -> first valid signal
        _bar(13, 108, 99, 101, 35),
    ]

    before_break = assess_bearish_weekly_structure(bars[:12], pivot_window=1)
    assert before_break.status != STATUS_CONFIRMED

    result = assess_bearish_weekly_structure(bars, pivot_window=1)
    assert result.status == STATUS_CONFIRMED
    assert result.signal_index == 12
    assert result.signal_timestamp == "W12"
    assert [p.kind for p in result.pivots] == ["H", "L", "H", "L", "H"]
    assert result.metadata["divergence"] is True
    assert result.metadata["order_authority"] is False
    assert result.metadata["broker_write_authority"] is False


def test_pattern_without_downside_break_does_not_signal():
    bars = [
        _bar(0, 105, 100, 103),
        _bar(1, 110, 101, 108),
        _bar(2, 120, 108, 116),
        _bar(3, 114, 104, 108),
        _bar(4, 109, 100, 103),
        _bar(5, 114, 104, 111),
        _bar(6, 119, 110, 116),
        _bar(7, 114, 107, 110),
        _bar(8, 111, 105, 108),
        _bar(9, 116, 109, 114),
        _bar(10, 120, 111, 117),
        _bar(11, 116, 108, 111),
        _bar(12, 112, 105, 107),
        _bar(13, 113, 106, 109),
    ]
    result = assess_bearish_weekly_structure(bars, pivot_window=1)
    assert result.status == STATUS_NO_SIGNAL
    assert result.signal_index is None


def test_non_contracting_swings_are_rejected():
    bars = [
        _bar(0, 105, 100, 103),
        _bar(1, 110, 101, 108),
        _bar(2, 120, 108, 116),
        _bar(3, 114, 104, 108),
        _bar(4, 109, 100, 103),
        _bar(5, 116, 105, 112),
        _bar(6, 130, 112, 125),  # expansion, not contraction
        _bar(7, 118, 106, 111),
        _bar(8, 112, 104, 108),
        _bar(9, 124, 110, 120),
        _bar(10, 135, 114, 130),  # expansion again
        _bar(11, 120, 106, 110),
        _bar(12, 111, 99, 100),
        _bar(13, 108, 97, 98),
    ]
    result = assess_bearish_weekly_structure(bars, pivot_window=1)
    assert result.status == STATUS_NO_SIGNAL

"""Synthetic hand-calculated tests for the independent scalar EMA oracle."""
import pytest

from research.verification_gateway.reference_math import ema_cross_up_reference
from core.indicators_live import compute_indicators


def test_sma_seed_and_recursive_warmup_are_explicit():
    result = ema_cross_up_reference([2, 4, 6, 8], fast_period=2, slow_period=3)
    assert result.fast[0] is None
    assert result.fast[1] == pytest.approx(3.0)
    assert result.fast[2] == pytest.approx(5.0)
    assert result.fast[3] == pytest.approx(7.0)
    assert result.slow[:2] == (None, None)
    assert result.slow[2] == pytest.approx(4.0)
    assert result.slow[3] == pytest.approx(6.0)
    assert result.cross_up_indices == ()


def test_cross_boundary_is_strict_and_uses_previous_complete_observation():
    # With periods 2/3 the fast line moves above the slow line at index 5.
    result = ema_cross_up_reference([6, 4, 2, 1, 4, 8], fast_period=2, slow_period=3)
    assert result.cross_up_indices == (5,)


def test_future_mutation_cannot_change_prior_reference_values_or_events():
    prefix = [6, 4, 2, 1, 4]
    original = ema_cross_up_reference(prefix + [8], fast_period=2, slow_period=3)
    mutated = ema_cross_up_reference(prefix + [1000], fast_period=2, slow_period=3)
    assert original.fast[:len(prefix)] == mutated.fast[:len(prefix)]
    assert original.slow[:len(prefix)] == mutated.slow[:len(prefix)]
    assert original.cross_up_indices == mutated.cross_up_indices


def test_independent_ema_matches_pure_existing_indicator_on_synthetic_prefixes():
    closes = [100, 101, 99, 102, 103, 100, 105, 104, 107, 106,
              110, 108, 111, 109, 113, 115, 112, 117, 116, 119,
              121, 118, 122, 124, 120, 126, 125, 129]
    reference = ema_cross_up_reference(closes, fast_period=5, slow_period=20)
    for prefix_end in range(20, len(closes) + 1):
        prefix = closes[:prefix_end]
        candles = [
            {"ts": index, "close": close, "high": close + 1,
             "low": close - 1, "volume": 10}
            for index, close in enumerate(prefix)
        ]
        observed = compute_indicators(
            candles, vwap_window=1, atr_period=1, adx_period=1,
            vol_window=1, slope_window=1,
        )["ema"]
        assert observed == pytest.approx(reference.slow[prefix_end - 1], abs=1e-12)


@pytest.mark.parametrize("closes", [[1, float("nan")], [1, float("inf")]])
def test_nonfinite_prices_fail_closed(closes):
    with pytest.raises(ValueError, match="finite"):
        ema_cross_up_reference(closes, fast_period=1, slow_period=2)


def test_invalid_period_order_fails_closed():
    with pytest.raises(ValueError, match="fast_period < slow_period"):
        ema_cross_up_reference([1, 2], fast_period=2, slow_period=2)

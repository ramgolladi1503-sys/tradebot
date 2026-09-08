from __future__ import annotations

import pandas as pd
import pytest

from research.macd_futures_participation_regime_v1.analysis import CampaignBlocked
from research.macd_futures_participation_regime_v1.matching import (
    validate_state_matching_coverage,
)


def _signals() -> pd.DataFrame:
    return pd.DataFrame({"signal_trade_id": ["S1", "S2"]})


def test_matching_gate_accepts_complete_well_supported_signals():
    per_signal = pd.DataFrame(
        {
            "signal_trade_id": ["S1", "S2"],
            "compatible_placebo_n": [80, 45],
        }
    )
    result = validate_state_matching_coverage(per_signal, _signals())
    assert result["matching_coverage_gate"] == "PASS"
    assert result["signal_coverage_fraction"] == 1.0
    assert result["minimum_compatible_placebos_observed"] == 45


def test_matching_gate_blocks_silent_signal_dropout():
    per_signal = pd.DataFrame(
        {"signal_trade_id": ["S1"], "compatible_placebo_n": [100]}
    )
    with pytest.raises(CampaignBlocked, match="ZERO_COMPATIBLE_PLACEBOS"):
        validate_state_matching_coverage(per_signal, _signals())


def test_matching_gate_blocks_thin_same_state_matching():
    per_signal = pd.DataFrame(
        {
            "signal_trade_id": ["S1", "S2"],
            "compatible_placebo_n": [19, 100],
        }
    )
    with pytest.raises(CampaignBlocked, match="INSUFFICIENT_COMPATIBLE_PLACEBOS"):
        validate_state_matching_coverage(per_signal, _signals())

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AtrContractSpec:
    version: str
    source: str
    timeframe: str
    true_range_policy: str
    first_bar_policy: str
    short_lookback: int
    long_lookback: int
    smoothing: str
    short_warmup_policy: str
    long_warmup_policy: str
    partial_window_policy: str
    zero_fill_policy: str
    session_policy: str
    missing_bar_policy: str
    invalid_bar_policy: str
    partial_session_policy: str
    output_unit: str
    rounding_policy: str
    serialization_policy: str


ATR_SHORT_LONG_V1 = AtrContractSpec(
    version="atr_short_long_v1",
    source="phase3a1_completed_underlying_index_session_bars",
    timeframe="1m",
    true_range_policy="max_of_high_low_high_prev_close_low_prev_close_after_first_bar",
    first_bar_policy="session_local_high_low",
    short_lookback=5,
    long_lookback=30,
    smoothing="simple_rolling_mean",
    short_warmup_policy="strict_full_window_5",
    long_warmup_policy="strict_full_window_30",
    partial_window_policy="forbidden",
    zero_fill_policy="forbidden",
    session_policy="reset_each_session",
    missing_bar_policy="break_contiguity_fail_closed",
    invalid_bar_policy="fail_closed",
    partial_session_policy="permitted_with_strict_contiguous_warmup",
    output_unit="underlying_price_points",
    rounding_policy="no_calculation_rounding",
    serialization_policy="stable_canonical_serialization_at_evidence_boundaries",
)


def validate_atr_contract(spec: AtrContractSpec) -> AtrContractSpec:
    if spec.version != "atr_short_long_v1":
        raise ValueError("unsupported_atr_contract_version")
    if spec.short_lookback != 5:
        raise ValueError("atr_short_long_v1_short_lookback_must_equal_5")
    if spec.long_lookback != 30:
        raise ValueError("atr_short_long_v1_long_lookback_must_equal_30")
    if spec.long_lookback <= spec.short_lookback:
        raise ValueError("atr_short_long_v1_long_lookback_must_exceed_short")
    if spec.timeframe != "1m":
        raise ValueError("atr_short_long_v1_timeframe_must_equal_1m")
    if spec.smoothing != "simple_rolling_mean":
        raise ValueError("atr_short_long_v1_smoothing_must_equal_simple_rolling_mean")
    if spec.first_bar_policy != "session_local_high_low":
        raise ValueError("atr_short_long_v1_first_bar_policy_must_equal_session_local_high_low")
    if spec.short_warmup_policy != "strict_full_window_5":
        raise ValueError("atr_short_long_v1_short_warmup_policy_must_equal_strict_full_window_5")
    if spec.long_warmup_policy != "strict_full_window_30":
        raise ValueError("atr_short_long_v1_long_warmup_policy_must_equal_strict_full_window_30")
    if spec.partial_window_policy != "forbidden":
        raise ValueError("atr_short_long_v1_partial_window_policy_must_forbid_partial_windows")
    if spec.zero_fill_policy != "forbidden":
        raise ValueError("atr_short_long_v1_zero_fill_policy_must_forbid_zero_fill")
    if spec.session_policy != "reset_each_session":
        raise ValueError("atr_short_long_v1_session_policy_must_reset_each_session")
    if spec.missing_bar_policy != "break_contiguity_fail_closed":
        raise ValueError("atr_short_long_v1_missing_bar_policy_must_break_contiguity_fail_closed")
    if spec.invalid_bar_policy != "fail_closed":
        raise ValueError("atr_short_long_v1_invalid_bar_policy_must_fail_closed")
    if spec.output_unit != "underlying_price_points":
        raise ValueError("atr_short_long_v1_output_unit_must_equal_underlying_price_points")
    if spec.rounding_policy != "no_calculation_rounding":
        raise ValueError("atr_short_long_v1_rounding_policy_must_disable_calculation_rounding")
    return spec


APPROVED_ATR_CONTRACT = validate_atr_contract(ATR_SHORT_LONG_V1)


__all__ = [
    "ATR_SHORT_LONG_V1",
    "APPROVED_ATR_CONTRACT",
    "AtrContractSpec",
    "validate_atr_contract",
]

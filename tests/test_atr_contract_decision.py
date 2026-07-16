from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from core.atr_contract import APPROVED_ATR_CONTRACT, ATR_SHORT_LONG_V1, validate_atr_contract
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol


REPO_ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_READER_FILES = {
    "strategies/movement/compression_breakout.py",
    "strategies/movement/event_volatility_expansion.py",
    "core/movement_regime.py",
    "core/runtime_snapshot_producer.py",
    "core/orchestrator.py",
}

PRODUCTION_DECLARATION_FILES = {
    "core/movement_contract.py",
}

NONAUTHORITATIVE_PROXY_FILES = {
    "core/orb_ohlcv_validation.py",
    "scripts/backtest_all_strategies_available_data.py",
}

GENERIC_ATR_RUNTIME_FILES = {
    "core/indicators_live.py",
    "core/market_data.py",
}

APPROVED_CANDIDATE_A = {
    "timeframe": "1m",
    "short_lookback": 5,
    "long_lookback": 30,
    "smoothing": "simple_rolling_mean",
    "selected": True,
}

REJECTED_CANDIDATE_B = {
    "timeframe": "1m",
    "short_lookback": 5,
    "long_lookback": 30,
    "smoothing": "wilder_recursive_moving_average",
    "selected": False,
}

REJECTED_CANDIDATE_C = {
    "timeframe": "1m",
    "short_lookback": 14,
    "long_lookback": 30,
    "smoothing": "simple_rolling_mean",
    "selected": False,
}


def _tracked_python_files() -> list[Path]:
    return [
        path
        for path in REPO_ROOT.rglob("*.py")
        if ".git" not in path.parts and "__pycache__" not in path.parts
    ]


def _files_referencing(field: str) -> set[str]:
    matches: set[str] = set()
    for path in _tracked_python_files():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        if field in text:
            matches.add(path.relative_to(REPO_ROOT).as_posix())
    return matches


def _runtime_missing_context():
    return _strategy_context_from_market_symbol(
        "NIFTY",
        {
            "spot": 22620.0,
            "ltp": 22620.0,
            "metadata": {
                "strategy_context_truth": {"atr": 70.0},
                "strategy_context_provenance": {
                    "atr": {"timeframe": "1m", "lookback": "ATR_PERIOD"}
                },
                "strategy_context_missing": {
                    "atr_short": {"status": "MISSING_SOURCE"},
                    "atr_long": {"status": "MISSING_SOURCE"},
                },
            },
        },
    )


def _strategy_context_truth_test_source() -> str:
    return (REPO_ROOT / "tests/test_strategy_context_truth.py").read_text()


def _candidate_phase2_ownership_source() -> str:
    return (REPO_ROOT / "tests/test_candidate_phase2_ownership.py").read_text()


def test_every_current_atr_short_reader_and_writer_is_accounted_for() -> None:
    actual = _files_referencing("atr_short")
    expected = (
        PRODUCTION_READER_FILES
        | PRODUCTION_DECLARATION_FILES
        | NONAUTHORITATIVE_PROXY_FILES
        | {"core/atr_contract.py", "core/market_data.py", "core/session_atr.py", "tests/test_atr_contract_decision.py"}
        | {
            "tests/test_captured_market_session_replay.py",
            "tests/test_captured_atr_replay.py",
            "tests/test_compression_trend_movement_strategies.py",
            "tests/test_event_late_day_movement_strategies.py",
            "tests/test_movement_regime.py",
            "tests/test_strategy_context_truth.py",
            "tests/test_session_atr_runtime.py",
                    "tests/test_strategy_missing_evidence_observability.py",
                    "tests/test_compression_breakout_phase3b_gap_audit.py",
                    "tests/test_compression_breakout_range_width_runtime_contract.py",
                        "tests/test_strategy_missing_evidence_policy.py",
                        "tests/test_strategy_profile_fail_closed.py",
                        "tests/test_strategy_registry_integrity.py",
                "tests/test_candidate_phase2_ownership.py",
                "tests/test_candidate_phase2_semantic_ownership.py",
                "tests/test_vwap_trap_movement_strategies.py",
                "tests/test_exhaustion_mean_reversion_strategies.py",
                "tests/test_phase3a3_atr_proofs.py",
            }
        )
    assert actual == expected


def test_every_current_atr_long_reader_and_writer_is_accounted_for() -> None:
    actual = _files_referencing("atr_long")
    expected = (
        PRODUCTION_READER_FILES
        | PRODUCTION_DECLARATION_FILES
        | NONAUTHORITATIVE_PROXY_FILES
        | {"core/market_data.py", "core/session_atr.py", "tests/test_atr_contract_decision.py"}
        | {
            "tests/test_captured_market_session_replay.py",
            "tests/test_captured_atr_replay.py",
            "tests/test_compression_trend_movement_strategies.py",
            "tests/test_event_late_day_movement_strategies.py",
            "tests/test_movement_regime.py",
            "tests/test_strategy_context_truth.py",
            "tests/test_session_atr_runtime.py",
                    "tests/test_strategy_missing_evidence_observability.py",
                    "tests/test_compression_breakout_phase3b_gap_audit.py",
                    "tests/test_compression_breakout_range_width_runtime_contract.py",
                        "tests/test_strategy_missing_evidence_policy.py",
                        "tests/test_strategy_profile_fail_closed.py",
                        "tests/test_strategy_registry_integrity.py",
                "tests/test_candidate_phase2_ownership.py",
                "tests/test_candidate_phase2_semantic_ownership.py",
                "tests/test_vwap_trap_movement_strategies.py",
                "tests/test_exhaustion_mean_reversion_strategies.py",
                "tests/test_phase3a3_atr_proofs.py",
            }
        )
    assert actual == expected


def test_contract_version_is_stable() -> None:
    assert ATR_SHORT_LONG_V1.version == "atr_short_long_v1"
    assert APPROVED_ATR_CONTRACT.version == "atr_short_long_v1"


def test_source_is_phase3a1_completed_underlying_bars() -> None:
    assert APPROVED_ATR_CONTRACT.source == "phase3a1_completed_underlying_index_session_bars"


def test_timeframe_is_one_minute() -> None:
    assert APPROVED_ATR_CONTRACT.timeframe == "1m"


def test_short_lookback_is_exactly_five() -> None:
    assert APPROVED_ATR_CONTRACT.short_lookback == 5


def test_long_lookback_is_exactly_thirty() -> None:
    assert APPROVED_ATR_CONTRACT.long_lookback == 30


def test_long_lookback_exceeds_short() -> None:
    assert APPROVED_ATR_CONTRACT.long_lookback > APPROVED_ATR_CONTRACT.short_lookback


def test_smoothing_is_simple_rolling_arithmetic_mean() -> None:
    assert APPROVED_ATR_CONTRACT.smoothing == "simple_rolling_mean"


def test_true_range_policy_is_explicit() -> None:
    assert (
        APPROVED_ATR_CONTRACT.true_range_policy
        == "max_of_high_low_high_prev_close_low_prev_close_after_first_bar"
    )


def test_first_bar_policy_is_session_local_high_low() -> None:
    assert APPROVED_ATR_CONTRACT.first_bar_policy == "session_local_high_low"


def test_warmup_is_strict_full_window() -> None:
    assert APPROVED_ATR_CONTRACT.short_warmup_policy == "strict_full_window_5"
    assert APPROVED_ATR_CONTRACT.long_warmup_policy == "strict_full_window_30"


def test_partial_window_values_are_forbidden() -> None:
    assert APPROVED_ATR_CONTRACT.partial_window_policy == "forbidden"


def test_zero_fill_is_forbidden() -> None:
    assert APPROVED_ATR_CONTRACT.zero_fill_policy == "forbidden"


def test_session_policy_resets_each_session() -> None:
    assert APPROVED_ATR_CONTRACT.session_policy == "reset_each_session"


def test_missing_minute_breaks_contiguity() -> None:
    assert APPROVED_ATR_CONTRACT.missing_bar_policy == "break_contiguity_fail_closed"


def test_short_availability_requires_five_consecutive_valid_bars() -> None:
    assert APPROVED_ATR_CONTRACT.short_warmup_policy == "strict_full_window_5"


def test_long_availability_requires_thirty_consecutive_valid_bars() -> None:
    assert APPROVED_ATR_CONTRACT.long_warmup_policy == "strict_full_window_30"


def test_duplicate_or_out_of_order_bars_fail_closed() -> None:
    assert APPROVED_ATR_CONTRACT.invalid_bar_policy == "fail_closed"


def test_invalid_ohlc_fails_closed() -> None:
    assert APPROVED_ATR_CONTRACT.invalid_bar_policy == "fail_closed"


def test_output_unit_is_underlying_points() -> None:
    assert APPROVED_ATR_CONTRACT.output_unit == "underlying_price_points"


def test_calculation_rounding_is_disabled() -> None:
    assert APPROVED_ATR_CONTRACT.rounding_policy == "no_calculation_rounding"


def test_contract_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        ATR_SHORT_LONG_V1.short_lookback = 7  # type: ignore[misc]


def test_contract_validation_rejects_short_lookback_other_than_five() -> None:
    with pytest.raises(ValueError, match="short_lookback"):
        validate_atr_contract(replace(ATR_SHORT_LONG_V1, short_lookback=6))


def test_contract_validation_rejects_long_lookback_other_than_thirty() -> None:
    with pytest.raises(ValueError, match="long_lookback"):
        validate_atr_contract(replace(ATR_SHORT_LONG_V1, long_lookback=31))


def test_contract_validation_rejects_wilder_smoothing_under_v1() -> None:
    with pytest.raises(ValueError, match="smoothing"):
        validate_atr_contract(
            replace(ATR_SHORT_LONG_V1, smoothing="wilder_recursive_moving_average")
        )


def test_contract_validation_rejects_continuous_cross_session_behaviour() -> None:
    with pytest.raises(ValueError, match="session_policy"):
        validate_atr_contract(replace(ATR_SHORT_LONG_V1, session_policy="continuous_across_sessions"))


def test_runtime_strategy_context_keeps_short_and_long_atr_missing() -> None:
    ctx = _runtime_missing_context()
    assert ctx.atr_short is None
    assert ctx.atr_long is None


def test_phase3a1_completed_history_boundary_is_unchanged() -> None:
    source = _strategy_context_truth_test_source()
    assert "def test_runtime_context_construction_opens_no_network_or_threads" in source
    assert "def test_direct_context_fingerprint_is_unchanged" in source


def test_movement_strategy_files_remain_unchanged() -> None:
    assert "MAX_ATR_RATIO" in (
        REPO_ROOT / "strategies/movement/compression_breakout.py"
    ).read_text()
    assert "MIN_ATR_EXPANSION_RATIO" in (
        REPO_ROOT / "strategies/movement/event_volatility_expansion.py"
    ).read_text()


def test_candidate_fingerprints_remain_unchanged() -> None:
    source = _strategy_context_truth_test_source()
    assert '(\"opening_range_retest_v1\", 0.328053, \"BUY_CALL\", \"VALIDATED_CANDIDATE\")' in source
    assert '(\"compression_breakout_v1\", 0.470676, \"BUY_CALL\", \"VALIDATED_CANDIDATE\")' in source
    assert '(\"trend_pullback_v1\", 0.648584, \"BUY_CALL\", \"VALIDATED_CANDIDATE\")' in source

    ownership_source = _candidate_phase2_ownership_source()
    assert "def _raw_setup_fingerprint()" in ownership_source
    assert '"opening_range_retest_v1"' in ownership_source
    assert '"compression_breakout_v1"' in ownership_source
    assert '"trend_pullback_v1"' in ownership_source
    assert "0.328053" not in ownership_source
    assert "0.470676" in ownership_source
    assert "0.648584" in ownership_source


def test_no_broker_network_order_execution_or_threads_are_added() -> None:
    source = (REPO_ROOT / "core/atr_contract.py").read_text()
    forbidden = (
        "socket",
        "threading",
        "requests",
        "broker",
        "order",
        "execute",
        "StrategyContext(",
    )
    assert all(token not in source for token in forbidden)


def test_generic_runtime_indicator_surface_only_defines_single_atr() -> None:
    market_data_text = (REPO_ROOT / "core/market_data.py").read_text()
    indicators_text = (REPO_ROOT / "core/indicators_live.py").read_text()
    assert "atr_period=getattr(cfg, \"ATR_PERIOD\", 14)" in market_data_text
    assert 'out["atr"] = atr' in indicators_text
    assert 'out["atr_short"]' not in indicators_text
    assert 'out["atr_long"]' not in indicators_text


def test_offline_proxy_writers_are_not_the_contract_and_still_show_rejected_behavior() -> None:
    orb_proxy_text = (REPO_ROOT / "core/orb_ohlcv_validation.py").read_text()
    backtest_proxy_text = (
        REPO_ROOT / "scripts/backtest_all_strategies_available_data.py"
    ).read_text()
    for text in (orb_proxy_text, backtest_proxy_text):
        assert "rolling(5, min_periods=3)" in text
        assert "rolling(30, min_periods=5)" in text
        assert "fillna(0.0)" in text


def test_candidate_a_is_the_approved_governance_choice() -> None:
    assert APPROVED_CANDIDATE_A["selected"] is True
    assert APPROVED_CANDIDATE_A["short_lookback"] == 5
    assert APPROVED_CANDIDATE_A["long_lookback"] == 30
    assert APPROVED_CANDIDATE_A["smoothing"] == "simple_rolling_mean"


def test_candidate_b_is_rejected() -> None:
    assert REJECTED_CANDIDATE_B["selected"] is False
    assert REJECTED_CANDIDATE_B["smoothing"] == "wilder_recursive_moving_average"


def test_candidate_c_is_rejected() -> None:
    assert REJECTED_CANDIDATE_C["selected"] is False
    assert REJECTED_CANDIDATE_C["short_lookback"] == 14
    assert REJECTED_CANDIDATE_C["long_lookback"] == 30

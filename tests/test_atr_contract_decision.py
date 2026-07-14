from __future__ import annotations

from pathlib import Path

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

BOUNDED_ALTERNATIVES = (
    {
        "name": "Candidate A",
        "timeframe": "1m completed underlying session bars",
        "short_lookback": 5,
        "long_lookback": 30,
        "smoothing": "simple rolling mean of true range",
        "first_session_bar": "SESSION_LOCAL",
        "session_behavior": "RESET_EACH_SESSION",
        "warm_up": "strict full-window warm-up",
        "advantages": "matches both discovered proxy writers exactly",
        "risks": "only proxy evidence; current proxy uses partial warm-up and zero fill that conflict with truthful missingness",
        "repository_evidence": (
            "core/orb_ohlcv_validation.py",
            "scripts/backtest_all_strategies_available_data.py",
        ),
        "consumers": (
            "compression_breakout_v1",
            "event_volatility_expansion_v1",
            "movement_regime",
        ),
    },
    {
        "name": "Candidate B",
        "timeframe": "1m completed underlying session bars",
        "short_lookback": 5,
        "long_lookback": 30,
        "smoothing": "Wilder recursive moving average",
        "first_session_bar": "SESSION_LOCAL",
        "session_behavior": "RESET_EACH_SESSION",
        "warm_up": "strict full-window warm-up",
        "advantages": "aligns with repository use of Wilder-style smoothing for other indicators",
        "risks": "no atr_short/atr_long implementation or test uses Wilder today",
        "repository_evidence": (
            "core/vectorized_signals.py",
            "core/indicators_live.py",
        ),
        "consumers": (
            "compression_breakout_v1",
            "event_volatility_expansion_v1",
            "movement_regime",
        ),
    },
    {
        "name": "Candidate C",
        "timeframe": "runtime OHLC buffer bars at the existing indicator cadence",
        "short_lookback": 14,
        "long_lookback": 30,
        "smoothing": "simple rolling mean of true range",
        "first_session_bar": "SESSION_LOCAL",
        "session_behavior": "RESET_EACH_SESSION",
        "warm_up": "strict full-window warm-up",
        "advantages": "reuses the existing runtime ATR family for the short leg",
        "risks": "repository never defines short=14 and long=30 as the short/long pair",
        "repository_evidence": (
            "core/indicators_live.py",
            "core/market_data.py",
        ),
        "consumers": (
            "compression_breakout_v1",
            "event_volatility_expansion_v1",
            "movement_regime",
        ),
    },
)


def _tracked_python_files() -> list[Path]:
    return [
        path
        for path in REPO_ROOT.rglob("*.py")
        if ".git" not in path.parts and "__pycache__" not in path.parts
    ]


def _files_referencing(field: str) -> set[str]:
    matches: set[str] = set()
    needle = field
    for path in _tracked_python_files():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        if needle in text:
            matches.add(path.relative_to(REPO_ROOT).as_posix())
    return matches


def test_every_current_atr_short_reader_and_writer_is_accounted_for() -> None:
    actual = _files_referencing("atr_short")
    expected = (
        PRODUCTION_READER_FILES
        | PRODUCTION_DECLARATION_FILES
        | NONAUTHORITATIVE_PROXY_FILES
        | {
            "tests/test_atr_contract_decision.py",
            "tests/test_captured_market_session_replay.py",
            "tests/test_compression_trend_movement_strategies.py",
            "tests/test_event_late_day_movement_strategies.py",
            "tests/test_movement_regime.py",
            "tests/test_strategy_context_truth.py",
            "tests/test_strategy_missing_evidence_observability.py",
            "tests/test_strategy_missing_evidence_policy.py",
            "tests/test_strategy_profile_fail_closed.py",
            "tests/test_strategy_registry_integrity.py",
            "tests/test_candidate_phase2_ownership.py",
            "tests/test_candidate_phase2_semantic_ownership.py",
            "tests/test_vwap_trap_movement_strategies.py",
            "tests/test_exhaustion_mean_reversion_strategies.py",
        }
    )
    assert actual == expected


def test_every_current_atr_long_reader_and_writer_is_accounted_for() -> None:
    actual = _files_referencing("atr_long")
    expected = (
        PRODUCTION_READER_FILES
        | PRODUCTION_DECLARATION_FILES
        | NONAUTHORITATIVE_PROXY_FILES
        | {
            "tests/test_atr_contract_decision.py",
            "tests/test_captured_market_session_replay.py",
            "tests/test_compression_trend_movement_strategies.py",
            "tests/test_event_late_day_movement_strategies.py",
            "tests/test_movement_regime.py",
            "tests/test_strategy_context_truth.py",
            "tests/test_strategy_missing_evidence_observability.py",
            "tests/test_strategy_missing_evidence_policy.py",
            "tests/test_strategy_profile_fail_closed.py",
            "tests/test_strategy_registry_integrity.py",
            "tests/test_candidate_phase2_ownership.py",
            "tests/test_candidate_phase2_semantic_ownership.py",
            "tests/test_vwap_trap_movement_strategies.py",
            "tests/test_exhaustion_mean_reversion_strategies.py",
        }
    )
    assert actual == expected


def test_bounded_alternatives_are_explicit_and_defensive() -> None:
    assert len(BOUNDED_ALTERNATIVES) == 3
    for alternative in BOUNDED_ALTERNATIVES:
        assert alternative["short_lookback"] > 0
        assert alternative["long_lookback"] > alternative["short_lookback"]
        assert alternative["timeframe"]
        assert alternative["smoothing"]
        assert alternative["first_session_bar"] in {"SESSION_LOCAL", "CROSS_SESSION", "UNAVAILABLE"}
        assert alternative["session_behavior"] in {"RESET_EACH_SESSION", "CONTINUOUS_ACROSS_SESSIONS"}
        assert alternative["warm_up"]
        assert alternative["advantages"]
        assert alternative["risks"]
        assert alternative["repository_evidence"]
        assert alternative["consumers"] == (
            "compression_breakout_v1",
            "event_volatility_expansion_v1",
            "movement_regime",
        )


def test_runtime_strategy_context_keeps_short_and_long_atr_missing() -> None:
    ctx = _strategy_context_from_market_symbol(
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

    assert ctx.atr == 70.0
    assert ctx.atr_short is None
    assert ctx.atr_long is None


def test_generic_runtime_indicator_surface_only_defines_single_atr() -> None:
    market_data_text = (REPO_ROOT / "core/market_data.py").read_text()
    indicators_text = (REPO_ROOT / "core/indicators_live.py").read_text()

    assert "atr_period=getattr(cfg, \"ATR_PERIOD\", 14)" in market_data_text
    assert "out[\"atr\"] = atr" in indicators_text
    assert "out[\"atr_short\"]" not in indicators_text
    assert "out[\"atr_long\"]" not in indicators_text


def test_offline_proxy_writers_define_simple_rolling_short_and_long_means() -> None:
    orb_proxy_text = (REPO_ROOT / "core/orb_ohlcv_validation.py").read_text()
    backtest_proxy_text = (
        REPO_ROOT / "scripts/backtest_all_strategies_available_data.py"
    ).read_text()

    for text in (orb_proxy_text, backtest_proxy_text):
        assert "true_range" in text
        assert "rolling(5" in text
        assert "rolling(30" in text
        assert "atr_short" in text
        assert "atr_long" in text

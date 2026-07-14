from __future__ import annotations

import logging
import socket
import threading
from dataclasses import replace

import core.strategy_parameter_profiles as parameter_profiles
import pytest
import strategies.strategy_registry as strategy_registry
from core.candidate_pool_orchestrator import (
    build_candidate_pool_report,
    get_default_candidate_generators,
)
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.opening_drive import generate_opening_drive_candidates
from strategies.movement.opening_range_breakout import (
    generate_opening_range_retest_candidates,
)
from strategies.movement.option_pressure import generate_option_pressure_candidates
from strategies.strategy_registry import validate_strategy_registry_integrity


def _regime(primary: str = "TREND_UP", **overrides: float) -> MovementRegimeResult:
    scores = {
        "TREND_UP": 0.0,
        "TREND_DOWN": 0.0,
        "RANGE": 0.0,
        "CHOP": 0.0,
        "COMPRESSION": 0.0,
        "VOLATILITY_EXPANSION": 0.0,
        "TRAP_RISK": 0.0,
        "EXHAUSTION_RISK": 0.0,
        "EXPIRY_CONTEXT": 0.0,
        "INCONCLUSIVE": 0.0,
    }
    scores.update(overrides)
    return MovementRegimeResult(schema_version=1, primary_regime=primary, scores=scores)


def _fixed_context() -> StrategyContext:
    return StrategyContext(
        symbol="NIFTY",
        spot_ltp=22620.0,
        open_price=22500.0,
        vwap=22540.0,
        day_high=22620.0,
        day_low=22460.0,
        orb_high=22600.0,
        orb_low=22460.0,
        nearest_resistance=22600.0,
        nearest_support=22590.0,
        range_width_pct=0.14,
        atr_short=35.0,
        atr_long=100.0,
        volume_z=1.5,
        option_ce_ltp=120.0,
        option_pe_ltp=90.0,
        ce_premium_change=12.0,
        pe_premium_change=0.0,
        ce_spread_pct=0.8,
        pe_spread_pct=0.8,
        ce_depth=1200.0,
        pe_depth=1200.0,
        option_ltp_age_sec=0.4,
        quote_source="live_option_tick",
        fallback_used=False,
        minutes_since_open=35,
    )


def _opening_drive_context() -> StrategyContext:
    return StrategyContext(
        symbol="NIFTY",
        spot_ltp=22620.0,
        open_price=22500.0,
        vwap=22540.0,
        orb_high=22600.0,
        orb_low=22460.0,
        volume_z=1.5,
        option_ce_ltp=120.0,
        option_pe_ltp=90.0,
        ce_premium_change=12.0,
        pe_premium_change=0.0,
        ce_spread_pct=0.8,
        pe_spread_pct=0.8,
        ce_depth=1200.0,
        pe_depth=1200.0,
        option_ltp_age_sec=0.4,
        quote_source="live_option_tick",
        fallback_used=False,
        minutes_since_open=8,
    )


def _fixed_regime() -> MovementRegimeResult:
    return _regime(
        primary="TREND_UP",
        TREND_UP=0.8,
        COMPRESSION=0.8,
        VOLATILITY_EXPANSION=0.45,
    )


def _fingerprint(report) -> list[tuple[str, float, str, str]]:
    return [
        (
            candidate.strategy_id,
            round(candidate.raw_score, 6),
            candidate.direction,
            candidate.status,
        )
        for candidate in report.candidates
        if candidate.direction in {"BUY_CALL", "BUY_PUT"}
    ]


def test_default_generators_preserve_phase1a_fingerprint():
    report = build_candidate_pool_report(
        _fixed_context(),
        _fixed_regime(),
        candidate_generators=get_default_candidate_generators(),
    )

    assert _fingerprint(report) == [
        ("opening_range_retest_v1", 0.639513, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("compression_breakout_v1", 0.675169, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("trend_pullback_v1", 0.719646, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("option_pressure_confirmation_v1", 0.81475, "BUY_CALL", "VALIDATED_CANDIDATE"),
    ]


def test_profile_value_drift_blocks_only_affected_generator_and_logs_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    drifted_defaults = dict(parameter_profiles.EMBEDDED_PROFILE_DEFAULTS["opening_range_retest_v1"])
    drifted_defaults["MIN_BREAKOUT_DISTANCE_PCT"] = 0.0099
    monkeypatch.setitem(
        parameter_profiles.EMBEDDED_PROFILE_DEFAULTS,
        "opening_range_retest_v1",
        drifted_defaults,
    )
    caplog.set_level(logging.WARNING, logger="core.strategy_parameter_profiles")

    assert generate_opening_range_retest_candidates(_fixed_context(), _fixed_regime()) == ()

    report = build_candidate_pool_report(
        _fixed_context(),
        _fixed_regime(),
        candidate_generators=get_default_candidate_generators(),
    )

    assert report.failed_generator_count == 0
    assert report.generator_count == 11
    assert report.movement_candidate_count == 3
    assert _fingerprint(report) == [
        ("compression_breakout_v1", 0.675169, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("trend_pullback_v1", 0.719646, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("option_pressure_confirmation_v1", 0.81475, "BUY_CALL", "VALIDATED_CANDIDATE"),
    ]
    assert (
        "event=PROFILE_RESOLUTION_BLOCKED runtime_strategy_id=opening_range_retest_v1 "
        "requested_profile_id=opening_range_retest_v1 "
        "resolution_classification=PROFILE_VALUE_DRIFT "
        "blocked_reason=profile_resolution_profile_value_drift"
    ) in caplog.text


def test_missing_alias_target_blocks_only_option_pressure_generator(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    aliases = dict(parameter_profiles.VALIDATED_COMPATIBILITY_PROFILE_ALIASES)
    aliases["option_pressure_confirmation_v1"] = "missing_profile_v1"
    monkeypatch.setattr(parameter_profiles, "VALIDATED_COMPATIBILITY_PROFILE_ALIASES", aliases)
    caplog.set_level(logging.WARNING, logger="core.strategy_parameter_profiles")

    assert generate_option_pressure_candidates(_fixed_context(), _fixed_regime()) == ()

    report = build_candidate_pool_report(
        _fixed_context(),
        _fixed_regime(),
        candidate_generators=get_default_candidate_generators(),
    )

    assert report.failed_generator_count == 0
    assert report.movement_candidate_count == 3
    assert _fingerprint(report) == [
        ("opening_range_retest_v1", 0.639513, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("compression_breakout_v1", 0.675169, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("trend_pullback_v1", 0.719646, "BUY_CALL", "VALIDATED_CANDIDATE"),
    ]
    assert (
        "event=PROFILE_RESOLUTION_BLOCKED runtime_strategy_id=option_pressure_confirmation_v1 "
        "requested_profile_id=option_pressure_confirmation_v1 "
        "resolution_classification=MISSING_PROFILE "
        "blocked_reason=profile_resolution_missing_profile"
    ) in caplog.text


def test_incomplete_profile_blocks_generator_without_embedded_default_fallback(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    opening_drive = parameter_profiles.DEFAULT_PROFILES["opening_drive_v1"]
    monkeypatch.setitem(
        parameter_profiles.DEFAULT_PROFILES,
        "opening_drive_v1",
        replace(
            opening_drive,
            params={"MAX_OPENING_DRIVE_MINUTES": 20},
        ),
    )
    monkeypatch.setitem(
        parameter_profiles.EMBEDDED_PROFILE_DEFAULTS,
        "opening_drive_v1",
        {"MAX_OPENING_DRIVE_MINUTES": 20},
    )
    caplog.set_level(logging.WARNING, logger="core.strategy_parameter_profiles")

    assert generate_opening_drive_candidates(_opening_drive_context(), _fixed_regime()) == ()
    assert (
        "event=PROFILE_RESOLUTION_BLOCKED runtime_strategy_id=opening_drive_v1 "
        "requested_profile_id=opening_drive_v1 "
        "resolution_classification=INCOMPLETE_PROFILE "
        "blocked_reason=profile_missing_required_keys:MIN_OPEN_MOVE_PCT,MIN_VWAP_ALIGNMENT_PCT"
    ) in caplog.text


def test_candidate_generation_does_not_call_source_parsing(monkeypatch: pytest.MonkeyPatch):
    def _fail(*_args, **_kwargs):
        raise AssertionError("source parsing must stay offline only")

    monkeypatch.setattr(strategy_registry, "_extract_embedded_profile_defaults", _fail)

    report = build_candidate_pool_report(
        _fixed_context(),
        _fixed_regime(),
        candidate_generators=get_default_candidate_generators(),
    )

    assert report.failed_generator_count == 0
    assert _fingerprint(report) == [
        ("opening_range_retest_v1", 0.639513, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("compression_breakout_v1", 0.675169, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("trend_pullback_v1", 0.719646, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("option_pressure_confirmation_v1", 0.81475, "BUY_CALL", "VALIDATED_CANDIDATE"),
    ]


def test_profile_validation_opens_no_network_connections_or_threads(
    monkeypatch: pytest.MonkeyPatch,
):
    thread_starts: list[str] = []

    def _fail_connection(*_args, **_kwargs):
        raise AssertionError("profile validation must not open network connections")

    original_thread_start = threading.Thread.start

    def _record_thread_start(self: threading.Thread):
        thread_starts.append(self.name)
        raise AssertionError("profile validation must not start threads")

    monkeypatch.setattr(socket, "create_connection", _fail_connection)
    monkeypatch.setattr(threading.Thread, "start", _record_thread_start)

    try:
        validate_strategy_registry_integrity()
    finally:
        monkeypatch.setattr(threading.Thread, "start", original_thread_start)

    assert thread_starts == []

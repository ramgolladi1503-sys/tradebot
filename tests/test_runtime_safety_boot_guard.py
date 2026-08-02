from __future__ import annotations

import json
import pytest

import core.runtime_safety_boot_guard as boot_guard
from core.runtime_safety_boot_guard import (
    assess_runtime_boot_safety,
    enforce_runtime_boot_safety,
    write_boot_safety_report,
)


class _Config:
    EXECUTION_MODE = "SIM"
    ALLOW_SYNTHETIC_CHAIN = False
    OFFHOURS_FORCE_ENABLE = False


def test_live_clean_env_is_allowed():
    decision = assess_runtime_boot_safety(mode="LIVE", config=_Config(), env={"LIVE_BROKER_ADAPTER_ACTIVE": "true", "MAX_DAILY_LOSS_PCT": "0.02"})

    assert decision.allowed is True
    assert decision.mode == "LIVE"
    assert decision.unsafe_flags == ()
    assert decision.fatal_reasons == ()
    assert decision.warnings == ()
    assert decision.is_order_action is False
    assert decision.append is False


def test_live_force_fallback_execution_fails_boot():
    decision = assess_runtime_boot_safety(
        mode="LIVE",
        config=_Config(),
        env={"FORCE_FALLBACK_EXECUTION": "true", "LIVE_BROKER_ADAPTER_ACTIVE": "true", "MAX_DAILY_LOSS_PCT": "0.02"},
    )

    assert decision.allowed is False
    assert "FORCE_FALLBACK_EXECUTION" in decision.unsafe_flags
    assert "LIVE_UNSAFE_FLAG:FORCE_FALLBACK_EXECUTION" in decision.fatal_reasons


def test_live_allow_stale_quotes_fails_boot():
    decision = assess_runtime_boot_safety(
        mode="LIVE",
        config=_Config(),
        env={"ALLOW_STALE_QUOTES": "1", "LIVE_BROKER_ADAPTER_ACTIVE": "true", "MAX_DAILY_LOSS_PCT": "0.02"},
    )

    assert decision.allowed is False
    assert "ALLOW_STALE_QUOTES" in decision.unsafe_flags
    assert "LIVE_UNSAFE_FLAG:ALLOW_STALE_QUOTES" in decision.fatal_reasons


def test_live_risk_gate_and_kill_switch_overrides_fail_boot():
    decision = assess_runtime_boot_safety(
        mode="LIVE",
        config=_Config(),
        env={"DISABLE_RISK_GATE": "yes", "DISABLE_KILL_SWITCH": "on", "LIVE_BROKER_ADAPTER_ACTIVE": "true", "MAX_DAILY_LOSS_PCT": "0.02"},
    )

    assert decision.allowed is False
    assert "DISABLE_RISK_GATE" in decision.unsafe_flags
    assert "DISABLE_KILL_SWITCH" in decision.unsafe_flags
    assert "LIVE_UNSAFE_FLAG:DISABLE_RISK_GATE" in decision.fatal_reasons
    assert "LIVE_UNSAFE_FLAG:DISABLE_KILL_SWITCH" in decision.fatal_reasons


def test_live_synthetic_option_alias_fails_boot_from_config():
    class Config(_Config):
        EXECUTION_MODE = "LIVE"
        ALLOW_SYNTHETIC_CHAIN = True

    decision = assess_runtime_boot_safety(mode="LIVE", config=Config(), env={"LIVE_BROKER_ADAPTER_ACTIVE": "true", "MAX_DAILY_LOSS_PCT": "0.02"})

    assert decision.allowed is False
    assert "ALLOW_SYNTHETIC_OPTION_QUOTES" in decision.unsafe_flags
    assert decision.unsafe_sources["ALLOW_SYNTHETIC_OPTION_QUOTES"] == ["ALLOW_SYNTHETIC_CHAIN"]
    assert "LIVE_UNSAFE_FLAG:ALLOW_SYNTHETIC_OPTION_QUOTES" in decision.fatal_reasons


def test_live_market_closed_execution_alias_fails_boot_from_config():
    class Config(_Config):
        EXECUTION_MODE = "LIVE"
        OFFHOURS_FORCE_ENABLE = True

    decision = assess_runtime_boot_safety(mode="LIVE", config=Config(), env={"LIVE_BROKER_ADAPTER_ACTIVE": "true", "MAX_DAILY_LOSS_PCT": "0.02"})

    assert decision.allowed is False
    assert "ALLOW_MARKET_CLOSED_EXECUTION" in decision.unsafe_flags
    assert decision.unsafe_sources["ALLOW_MARKET_CLOSED_EXECUTION"] == ["OFFHOURS_FORCE_ENABLE"]
    assert "LIVE_UNSAFE_FLAG:ALLOW_MARKET_CLOSED_EXECUTION" in decision.fatal_reasons


def test_paper_unsafe_flags_warn_but_do_not_fail_boot():
    decision = assess_runtime_boot_safety(
        mode="PAPER",
        config=_Config(),
        env={"ALLOW_STALE_QUOTES": "true", "DISABLE_RISK_GATE": "true"},
    )

    assert decision.allowed is True
    assert "ALLOW_STALE_QUOTES" in decision.unsafe_flags
    assert "DISABLE_RISK_GATE" in decision.unsafe_flags
    assert decision.fatal_reasons == ()
    assert "NON_LIVE_UNSAFE_FLAG:ALLOW_STALE_QUOTES" in decision.warnings
    assert "NON_LIVE_UNSAFE_FLAG:DISABLE_RISK_GATE" in decision.warnings


def test_sim_unsafe_flags_warn_but_do_not_fail_boot():
    decision = assess_runtime_boot_safety(
        mode="SIM",
        config=_Config(),
        env={"ALLOW_MARKET_CLOSED_EXECUTION": "true"},
    )

    assert decision.allowed is True
    assert "ALLOW_MARKET_CLOSED_EXECUTION" in decision.unsafe_flags
    assert "NON_LIVE_UNSAFE_FLAG:ALLOW_MARKET_CLOSED_EXECUTION" in decision.warnings


def test_invalid_mode_fails_closed():
    decision = assess_runtime_boot_safety(mode="MONEY_PRINTER", config=_Config(), env={})

    assert decision.allowed is False
    assert decision.mode == "INVALID"
    assert "INVALID_EXECUTION_MODE" in decision.fatal_reasons


def test_write_boot_safety_report_writes_json(tmp_path):
    decision = assess_runtime_boot_safety(mode="PAPER", config=_Config(), env={"ALLOW_STALE_QUOTES": "true"})
    path = tmp_path / "runtime_boot_safety_latest.json"

    written = write_boot_safety_report(decision, path=path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert written == path
    assert payload["schema_version"] == 1
    assert payload["allowed"] is True
    assert payload["mode"] == "PAPER"
    assert payload["unsafe_flags"] == ["ALLOW_STALE_QUOTES"]
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert "ts" in payload


def test_enforce_runtime_boot_safety_raises_and_writes_report_on_live_failure(tmp_path):
    path = tmp_path / "runtime_boot_safety_latest.json"

    with pytest.raises(RuntimeError) as exc_info:
        enforce_runtime_boot_safety(
            mode="LIVE",
            config=_Config(),
            env={"DISABLE_RISK_GATE": "true", "LIVE_BROKER_ADAPTER_ACTIVE": "true", "MAX_DAILY_LOSS_PCT": "0.02"},
            report_path=path,
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "runtime_boot_safety_failed" in str(exc_info.value)
    assert payload["allowed"] is False
    assert payload["mode"] == "LIVE"
    assert payload["fatal_reasons"] == ["LIVE_UNSAFE_FLAG:DISABLE_RISK_GATE"]


def test_live_fails_without_broker_adapter():
    decision = assess_runtime_boot_safety(
        mode="LIVE",
        config=_Config(),
        env={"MAX_DAILY_LOSS_PCT": "0.02"},
    )
    assert decision.allowed is False
    assert "LIVE_BROKER_ADAPTER_NOT_CONFIGURED" in decision.fatal_reasons


def test_live_fails_without_drawdown_limit():
    decision = assess_runtime_boot_safety(
        mode="LIVE",
        config=_Config(),
        env={"LIVE_BROKER_ADAPTER_ACTIVE": "true", "MAX_DAILY_LOSS_PCT": "0.10"},
    )
    assert decision.allowed is False
    assert "LIVE_GLOBAL_DRAWDOWN_LIMIT_UNSAFE" in decision.fatal_reasons


def test_mapping_config_is_supported_and_environment_can_be_none():
    config = {
        "EXECUTION_MODE": "PAPER",
        "ALLOW_SYNTHETIC_CHAIN": True,
    }

    assert boot_guard._env_value(None, "EXECUTION_MODE") is None
    decision = assess_runtime_boot_safety(mode=None, config=config, env={})

    assert decision.mode == "PAPER"
    assert decision.allowed is True
    assert decision.unsafe_sources["ALLOW_SYNTHETIC_OPTION_QUOTES"] == ["ALLOW_SYNTHETIC_CHAIN"]


def test_explicit_false_environment_value_overrides_true_config_alias():
    config = {"ALLOW_STALE_QUOTES": True}

    decision = assess_runtime_boot_safety(
        mode="PAPER",
        config=config,
        env={"ALLOW_STALE_QUOTES": "false"},
    )

    assert decision.allowed is True
    assert "ALLOW_STALE_QUOTES" not in decision.unsafe_flags


def test_startup_event_failure_cannot_override_safe_boot_decision(monkeypatch, tmp_path):
    import core.runtime_startup_lifecycle as lifecycle

    def fail_record(*_args, **_kwargs):
        raise RuntimeError("telemetry unavailable")

    monkeypatch.setattr(lifecycle, "record_runtime_startup_event", fail_record)

    decision = enforce_runtime_boot_safety(
        mode="PAPER",
        config=_Config(),
        env={},
        report_path=tmp_path / "boot.json",
    )

    assert decision.allowed is True

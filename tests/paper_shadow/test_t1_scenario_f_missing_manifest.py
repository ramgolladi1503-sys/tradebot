"""Cross-issue Scenario F: missing T-1 source remains blocked through registry."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.market_heritage_graph import load_verified_t1_prerequisites
from core.candidate_audits.intraday_opening_drive import CANDIDATE_ID as OPENING_DRIVE_ID
from core.candidate_audits.nifty_overnight_drift import CANDIDATE_S1_ID, CANDIDATE_S4_ID
from core.paper_shadow.strategy_shadow_adapter import StrategyShadowAdapterRegistry


def _observer_contracts():
    root = Path(__file__).resolve().parents[2]
    paths = {
        OPENING_DRIVE_ID: root / "docs/research/candidates/INTRADAY_OPENING_DRIVE_V1/FROZEN_SPEC.json",
        CANDIDATE_S1_ID: root / "docs/research/candidates/S1_MOMENTUM_OVERNIGHT_V1/FROZEN_SPEC.json",
        CANDIDATE_S4_ID: root / "docs/research/candidates/S4_MONDAY_OVERNIGHT_V1/FROZEN_SPEC.json",
    }
    return {strategy_id: hashlib.sha256(path.read_bytes()).hexdigest() for strategy_id, path in paths.items()}


def _missing_t1_result(tmp_path):
    contracts = _observer_contracts()
    required = {
        OPENING_DRIVE_ID: {
            "opening_drive_prev_contract_key": contracts[OPENING_DRIVE_ID],
            "opening_drive_prev_close_1529": contracts[OPENING_DRIVE_ID],
        },
        CANDIDATE_S1_ID: {
            "overnight_prev_daily_close": contracts[CANDIDATE_S1_ID],
            "overnight_prev_sma200": contracts[CANDIDATE_S1_ID],
        },
        CANDIDATE_S4_ID: {
            "overnight_prev_daily_close": contracts[CANDIDATE_S4_ID],
            "overnight_prev_sma200": contracts[CANDIDATE_S4_ID],
        },
    }
    return load_verified_t1_prerequisites(
        manifest_path=None,
        expected_manifest_sha256=None,
        approved_root=tmp_path,
        target_session={"trading_date": "2026-10-01", "venue": "NSE"},
        decision_epoch=1790832600.0,
        required_fields=required,
        target_instruments={
            OPENING_DRIVE_ID: {"contract_key": ""},
            CANDIDATE_S1_ID: {"symbol": "NIFTY50", "basis": "INDEX"},
            CANDIDATE_S4_ID: {"symbol": "NIFTY50", "basis": "INDEX"},
        },
    )


def test_missing_t1_source_blocks_all_dependent_strategies_and_is_recorded(tmp_path):
    loaded = _missing_t1_result(tmp_path)
    verification = loaded.pop("heritage_verification")

    registry = StrategyShadowAdapterRegistry(
        session_id="SCENARIO_F_MISSING_T1",
        source_sha="offline-scenario-fixture",
        evidence_root=tmp_path / "shadow",
        opening_drive_prev_contract_key=loaded["opening_drive_prev_contract_key"],
        opening_drive_prev_close_1529=loaded["opening_drive_prev_close_1529"],
        opening_drive_target_expiry=loaded["opening_drive_target_expiry"],
        overnight_prev_daily_close=loaded["overnight_prev_daily_close"],
        overnight_prev_sma200=loaded["overnight_prev_sma200"],
        prerequisite_verification=verification,
    )

    assert verification["status"] == "BLOCKED"
    assert verification["reason"] == "PINNED_HERITAGE_MANIFEST_REQUIRED"
    assert verification["read_only"] is True
    assert verification["is_order_action"] is False
    assert verification["broker_api_called"] is False
    assert verification["allowed_for_live_execution"] is False
    assert verification["strategy_readiness"] == {}
    assert all(value is None for value in loaded.values())
    assert registry.adapters == {}
    assert set(registry.disabled_strategies) == {
        OPENING_DRIVE_ID, CANDIDATE_S1_ID, CANDIDATE_S4_ID,
    }
    assert all(reason.startswith("DISABLED_FAIL_CLOSED:") for reason in registry.disabled_strategies.values())

    persisted = json.loads((tmp_path / "shadow" / "registry.json").read_text(encoding="utf-8"))
    assert persisted["prerequisite_verification"]["reason"] == "PINNED_HERITAGE_MANIFEST_REQUIRED"
    assert persisted["disabled_strategies"] == registry.disabled_strategies
    assert persisted["read_only"] is True
    assert persisted["broker_write_authority"] is False
    assert persisted["order_authority"] is False
    assert persisted["paper_authorized"] is False
    assert persisted["live_authorized"] is False
    assert registry.orders_placed == registry.orders_modified == registry.orders_cancelled == 0


def test_unverified_legacy_values_cannot_arm_strategies(tmp_path):
    loaded = _missing_t1_result(tmp_path)
    verification = loaded.pop("heritage_verification")
    registry = StrategyShadowAdapterRegistry(
        session_id="SCENARIO_F_LEGACY_VALUE_ATTACK",
        source_sha="offline-scenario-fixture",
        evidence_root=tmp_path / "shadow",
        opening_drive_prev_contract_key="NIFTY-FUTURE-UNKNOWN",
        opening_drive_prev_close_1529=25000.0,
        opening_drive_target_expiry="2026-10-29",
        overnight_prev_daily_close=25000.0,
        overnight_prev_sma200=24000.0,
        prerequisite_verification=verification,
    )

    assert registry.adapters == {}
    assert set(registry.disabled_strategies) == {
        OPENING_DRIVE_ID, CANDIDATE_S1_ID, CANDIDATE_S4_ID,
    }
    assert all(value["status"] == "BLOCKED" for value in verification["strategy_readiness"].values()) if verification["strategy_readiness"] else verification["status"] == "BLOCKED"
    assert registry.orders_placed == registry.orders_modified == registry.orders_cancelled == 0

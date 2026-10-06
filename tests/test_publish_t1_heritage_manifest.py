"""Tests for automated T-1 market heritage manifest publishing and verification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.candidate_audits.intraday_opening_drive import CANDIDATE_ID as OPENING_DRIVE_ID
from core.candidate_audits.nifty_overnight_drift import CANDIDATE_S1_ID, CANDIDATE_S4_ID
from core.market_heritage_graph import (
    load_verified_t1_prerequisites,
)
from core.market_heritage_verifier import verify_market_heritage_manifest
from core.paper_shadow.strategy_shadow_adapter import StrategyShadowAdapterRegistry
from scripts.publish_t1_heritage_manifest import (
    build_t1_heritage_graph,
    generate_rolling_close_dates,
    publish_t1_manifest,
)


def _load_contracts(repo_root: Path) -> dict[str, str]:
    paths = {
        OPENING_DRIVE_ID: repo_root / "docs/research/candidates/INTRADAY_OPENING_DRIVE_V1/FROZEN_SPEC.json",
        CANDIDATE_S1_ID: repo_root / "docs/research/candidates/S1_MOMENTUM_OVERNIGHT_V1/FROZEN_SPEC.json",
        CANDIDATE_S4_ID: repo_root / "docs/research/candidates/S4_MONDAY_OVERNIGHT_V1/FROZEN_SPEC.json",
    }
    return {
        strategy_id: hashlib.sha256(path.read_bytes()).hexdigest()
        for strategy_id, path in paths.items()
    }


def test_generate_rolling_close_dates_returns_200_weekdays():
    dates = generate_rolling_close_dates("2026-10-06", window=200)
    assert len(dates) == 200
    assert dates[-1] == "2026-10-06"
    assert dates == sorted(dates)


def test_build_and_publish_t1_manifest_end_to_end(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    target_date = "2026-10-07"
    source_date = "2026-10-06"
    futures_key = "NIFTY26OCTFUT"
    futures_close = 22776.1
    daily_close = 22776.1
    sma200 = 24473.368
    decision_epoch = 1791300000.0

    res = publish_t1_manifest(
        target_date=target_date,
        source_date=source_date,
        futures_contract_key=futures_key,
        futures_1529_close=futures_close,
        daily_close=daily_close,
        sma200_value=sma200,
        approved_root=tmp_path,
        run_id="test_run_t1",
        repo_root=repo_root,
        decision_epoch=decision_epoch,
    )

    assert res["status"] == "PUBLISHED_VERIFIED"
    assert res["read_only"] is True
    assert res["is_order_action"] is False
    assert res["broker_api_called"] is False
    assert res["allowed_for_live_execution"] is False

    manifest_path = Path(res["manifest_path"])
    assert manifest_path.is_file()
    assert res["manifest_sha256"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    manifest_doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_doc["session_identity"]["trading_date"] == target_date
    verification = verify_market_heritage_manifest(
        manifest_path,
        decision_epoch=decision_epoch,
    )
    assert verification["verdict"] == "PASS"

    contracts = _load_contracts(repo_root)
    required_fields = {
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
    target_instruments = {
        OPENING_DRIVE_ID: {"contract_key": futures_key},
        CANDIDATE_S1_ID: {"symbol": "NIFTY50", "basis": "INDEX"},
        CANDIDATE_S4_ID: {"symbol": "NIFTY50", "basis": "INDEX"},
    }

    loaded = load_verified_t1_prerequisites(
        manifest_path=manifest_path,
        expected_manifest_sha256=res["manifest_sha256"],
        approved_root=tmp_path,
        target_session={"trading_date": target_date, "venue": "NSE", "calendar_id": "NSE-HIST", "calendar_version": "v4"},
        decision_epoch=decision_epoch,
        required_fields=required_fields,
        target_instruments=target_instruments,
    )

    h_verif = loaded.pop("heritage_verification")
    assert h_verif["status"] == "VERIFIED"
    assert h_verif["read_only"] is True
    assert h_verif["is_order_action"] is False
    assert h_verif["broker_api_called"] is False
    assert h_verif["allowed_for_live_execution"] is False

    assert loaded["opening_drive_prev_contract_key"] == futures_key
    assert loaded["opening_drive_prev_close_1529"] == futures_close
    assert loaded["overnight_prev_daily_close"] == daily_close
    assert loaded["overnight_prev_sma200"] == sma200

    for strat in [OPENING_DRIVE_ID, CANDIDATE_S1_ID, CANDIDATE_S4_ID]:
        assert h_verif["strategy_readiness"][strat]["status"] == "READY"

    # Verify StrategyShadowAdapterRegistry arms all 3 strategies with ready prerequisites
    registry = StrategyShadowAdapterRegistry(
        session_id="SCENARIO_PROVEN_T1",
        source_sha="proven-t1-fixture",
        evidence_root=tmp_path / "shadow",
        opening_drive_prev_contract_key=loaded["opening_drive_prev_contract_key"],
        opening_drive_prev_close_1529=loaded["opening_drive_prev_close_1529"],
        opening_drive_target_expiry=loaded["opening_drive_target_expiry"],
        overnight_prev_daily_close=loaded["overnight_prev_daily_close"],
        overnight_prev_sma200=loaded["overnight_prev_sma200"],
        prerequisite_verification=h_verif,
    )

    assert set(registry.adapters.keys()) == {OPENING_DRIVE_ID, CANDIDATE_S1_ID, CANDIDATE_S4_ID}
    assert registry.disabled_strategies == {}
    assert registry.orders_placed == 0
    assert registry.orders_modified == 0
    assert registry.orders_cancelled == 0

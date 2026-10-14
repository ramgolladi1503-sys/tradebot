"""Offline production-path tests for option identity, capture-time cutoffs, and audit output."""

import glob
import json
from datetime import date, time as dtime

import pandas as pd
import pytest

from core.active_position_manager import ActivePositionManager, STATE_IN_FLIGHT, STATE_STANDBY
from core.nse_fo_contract_master import VerifiedCaptureAuthority, contract_key
import scripts.run_live_feed_advisor as advisor_module
from scripts.run_live_feed_advisor import SentinelLiveFeedAdvisor


@pytest.fixture
def advisor(tmp_path):
    """Build an advisor without constructor capture hashing or runtime WAL access."""
    instance = SentinelLiveFeedAdvisor.__new__(SentinelLiveFeedAdvisor)
    instance.ticker = "NIFTY"
    instance.target_expiry = "13 OCT 26"
    instance.apm = ActivePositionManager(wal_path=str(tmp_path / "apm-test-wal.json"))
    instance.spread_threshold = 0.04
    instance.last_exit_price = 22400.0
    instance.audit_log_path = tmp_path / "audit.jsonl"
    manifest_hash = "a" * 64
    entry = {
        "contract_key": contract_key("NIFTY", "2026-10-13", 22400, "CE"),
        "underlying": "NIFTY",
        "expiry": "2026-10-13",
        "strike": "22400",
        "option_type": "CE",
        "nse_instrument_id": "NSE-12345",
        "nse_permitted_to_trade": True,
        "nse_deleted": False,
        "nse_normal_market_trading_status": 2,
        "nse_normal_market_eligible": True,
        "upstox_instrument_key": "NSE_FO|44598",
        "upstox_trading_symbol": "NIFTY 22400 CE 13 OCT 26",
    }
    instance.contract_authority = VerifiedCaptureAuthority(
        manifest_sha256=manifest_hash,
        session_date=date(2026, 10, 13),
        nse_metadata={
            "artifact_filename": "NSE_FO_contract_09102026.csv.gz",
            "file_url": "https://nsearchives.nseindia.com/content/fo/NSE_FO_contract_09102026.csv.gz",
            "trading_date": "2026-10-09",
            "report_current_date": "2026-10-09",
            "report_future_date": "2026-10-13",
            "schema_version": "NSE_MII_FO_CONTRACT_V1",
            "file_sha256": "b" * 64,
            "listing_artifact_filename": "nse_fo_reports_2026-10-13.json",
            "listing_sha256": "d" * 64,
        },
        upstox_metadata={
            "artifact_filename": "upstox_complete_20261013.json.gz",
            "source_url": "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz",
            "downloaded_at_utc": "2026-10-13T03:30:00+00:00",
            "sha256": "c" * 64,
            "live_identity_eligible": True,
        },
        selected_by_instrument_key={"NSE_FO|44598": entry},
    )
    return instance


def quote_row(*, ts=1728445800.0, symbol="NIFTY 22400 CE 13 OCT 26", token="NSE_FO|44598", ltp=182.5):
    return {
        "ts": ts,
        "token": token,
        "symbol": symbol,
        "ltp": ltp,
        "bid": ltp - 0.5,
        "ask": ltp + 0.5,
        "vol": 1500.0,
        "oi": 60000.0,
        "contract_authority_manifest_sha256": "a" * 64,
    }


def route_synthetic_capture(monkeypatch, frame, authority):
    """Route the real file resolver to deterministic in-memory rows, without capture I/O."""
    monkeypatch.setattr(glob, "glob", lambda pattern: ["synthetic-capture.parquet"])
    monkeypatch.setattr(pd, "read_parquet", lambda _path: frame.copy())
    monkeypatch.setattr(advisor_module, "load_verified_capture_authority", lambda *_args: authority)


def test_expiry_is_resolved_from_unique_captured_contract_symbol(advisor):
    advisor.target_expiry = None
    frame = pd.DataFrame([
        quote_row(ts=1728445795.0),
        quote_row(ts=1728445800.0, ltp=183.0),
    ])

    result = advisor.resolve_quote_from_dataframe(frame, 22400, "CE")

    assert result["expiry"] == "13 OCT 26"
    assert result["expiry_source"] == "NSE_FO_MII_CONTRACT_MASTER"
    assert result["ltp"] == 183.0


def test_missing_identity_or_conflicting_token_fails_closed(advisor):
    advisor.target_expiry = None
    missing = pd.DataFrame([quote_row(symbol="NIFTY 22400 CE")])
    conflicting_token = pd.DataFrame([
        quote_row(),
        quote_row(ts=1728445801.0, token="NSE_FO|99999", ltp=183.0),
    ])

    assert advisor.resolve_quote_from_dataframe(missing, 22400, "CE") is None
    assert advisor.resolve_quote_from_dataframe(conflicting_token, 22400, "CE") is None
    assert advisor.resolve_quote_from_dataframe(missing, 22400, "CE", expiry="   ") is None


@pytest.mark.parametrize("missing_column", ["symbol", "token"])
def test_missing_contract_identity_columns_fail_closed(advisor, missing_column):
    frame = pd.DataFrame([quote_row()]).drop(columns=[missing_column])

    assert advisor.resolve_quote_from_dataframe(frame, 22400, "CE") is None


def test_explicit_iso_expiry_normalizes_to_instrument_master_label(advisor):
    frame = pd.DataFrame([quote_row()])

    result = advisor.resolve_quote_from_dataframe(frame, 22400, "CE", expiry="2026-10-13")

    assert result["expiry"] == "13 OCT 26"
    assert result["expiry_source"] == "NSE_FO_MII_CONTRACT_MASTER"


def test_explicit_expiry_resolves_exact_identity_and_token(advisor):
    frame = pd.DataFrame([
        quote_row(),
        quote_row(symbol="NIFTY 22400 CE 20 OCT 26", token="NSE_FO|44605", ltp=210.5),
        quote_row(symbol="NIFTY 22400 CE 13 OCT 26 EXTRA", token="NSE_FO|77777", ltp=190),
    ])

    result = advisor.resolve_quote_from_dataframe(frame, 22400, "CE", expiry="13 OCT 26")

    assert result["symbol"] == "NIFTY 22400 CE 13 OCT 26"
    assert result["token"] == "NSE_FO|44598"
    assert result["ltp"] == 182.5


def test_cutoff_filters_future_identity_and_token_before_uniqueness(advisor):
    cutoff = 1728445800.0
    frame = pd.DataFrame([
        quote_row(ts=cutoff - 5, token="NSE_FO|44598", ltp=180),
        quote_row(ts=cutoff + 1, token="NSE_FO|99999", ltp=190),
        quote_row(ts=cutoff + 2, symbol="NIFTY 22400 CE 20 OCT 26", token="NSE_FO|44605"),
    ])

    result = advisor.resolve_quote_from_dataframe(
        frame, 22400, "CE", expiry="13 OCT 26", decision_cutoff_epoch=cutoff
    )

    assert result is not None
    assert result["token"] == "NSE_FO|44598"
    assert result["timestamp"] == cutoff - 5


@pytest.mark.parametrize(
    "frame,cutoff",
    [
        (pd.DataFrame([{k: v for k, v in quote_row().items() if k != "ts"}]), 1728445800.0),
        (pd.DataFrame([quote_row(ts="not-a-timestamp")]), 1728445800.0),
        (pd.DataFrame([quote_row(ts=float("inf"))]), 1728445800.0),
        (pd.DataFrame([quote_row(ts=1728445801.0)]), 1728445800.0),
        (pd.DataFrame([quote_row()]), float("nan")),
    ],
)
def test_cutoff_requires_valid_finite_capture_timestamps(advisor, frame, cutoff):
    assert advisor.resolve_quote_from_dataframe(
        frame, 22400, "CE", expiry="13 OCT 26", decision_cutoff_epoch=cutoff
    ) is None


def test_missing_capture_timestamp_without_cutoff_fails_closed(advisor):
    frame = pd.DataFrame([{k: v for k, v in quote_row().items() if k != "ts"}])

    assert advisor.resolve_quote_from_dataframe(frame, 22400, "CE", expiry="13 OCT 26") is None


@pytest.mark.parametrize("field", ["ltp", "vol", "oi"])
def test_nonfinite_quote_measurement_fails_closed(advisor, field):
    row = quote_row()
    row[field] = float("inf")

    assert advisor.resolve_quote_from_dataframe(
        pd.DataFrame([row]), 22400, "CE", expiry="13 OCT 26"
    ) is None


def test_conflicting_tokens_for_exact_symbol_fail_closed(advisor):
    frame = pd.DataFrame([
        quote_row(ts=1728445795.0, token="NSE_FO|44598"),
        quote_row(ts=1728445799.0, token="NSE_FO|99999", ltp=183),
    ])

    assert advisor.resolve_quote_from_dataframe(
        frame, 22400, "CE", expiry="13 OCT 26", decision_cutoff_epoch=1728445800.0
    ) is None


def test_live_resolver_and_candidate_evaluation_use_same_production_path(advisor, monkeypatch):
    advisor.target_expiry = None
    cutoff = 1728445860.0
    route_synthetic_capture(monkeypatch, pd.DataFrame([quote_row(ts=cutoff - 5)]), advisor.contract_authority)

    result = advisor.evaluate_option_candidate(
        entry_dir="CE",
        chosen_strike=22400,
        contract_choice="NIFTY 22400 CE [ITM]",
        signal_display="BUY NIFTY 22400 CE [ITM] @ Breakout",
        bar_close_cutoff_epoch=cutoff,
        spot_close=22441.20,
        bar_time_str="2026-10-09T09:46:00+05:30",
        sl_pts=30.0,
        target_pts=60.0,
        total_drag_pts=3.5,
        current_gear="GEAR_2_TREND",
        btime=dtime(9, 46),
    )

    assert result["candidate_status"] == "CAPTURE_RECEIVE_TIME_REPLAY_ONLY"
    assert result["option_candidate"]["contract"] == "NIFTY 22400 CE 13 OCT 26"
    assert result["option_candidate"]["expiry"] == "13 OCT 26"
    assert result["option_candidate"]["expiry_source"] == "NSE_FO_MII_CONTRACT_MASTER"
    assert result["option_candidate"]["contract_authority_manifest_sha256"] == "a" * 64
    assert result["option_candidate"]["nse_contract_file_sha256"] == "b" * 64
    assert result["option_candidate"]["upstox_master_sha256"] == "c" * 64
    assert result["option_candidate"]["source_capture_ts"] <= cutoff
    assert result["option_candidate"]["capture_time_basis"] == "WEBSOCKET_ON_MESSAGE_CALLBACK_TIME"
    assert result["option_candidate"]["receive_time_verified"] is True
    assert result["option_candidate"]["exchange_event_time_verified"] is False
    assert advisor.apm.state == STATE_IN_FLIGHT
    assert advisor.apm.payload.position_id == "TRADE_0946_CE"


def test_unresolved_candidate_is_not_evaluable_and_does_not_arm(advisor, monkeypatch):
    route_synthetic_capture(monkeypatch, pd.DataFrame([quote_row(ts=1728445861.0)]), advisor.contract_authority)

    result = advisor.evaluate_option_candidate(
        entry_dir="CE",
        chosen_strike=22400,
        contract_choice="NIFTY 22400 CE [ITM]",
        signal_display="BUY NIFTY 22400 CE [ITM] @ Breakout",
        bar_close_cutoff_epoch=1728445860.0,
        spot_close=22441.20,
        bar_time_str="2026-10-09T09:46:00+05:30",
        sl_pts=30.0,
        target_pts=60.0,
        total_drag_pts=3.5,
        current_gear="GEAR_2_TREND",
        btime=dtime(9, 46),
    )

    assert result["candidate_status"] == "NOT_EVALUABLE"
    assert "OPTION_QUOTE_NOT_EVALUABLE" in result["signal_display"]
    assert result["option_candidate"] is None
    assert advisor.apm.state == STATE_STANDBY
    assert advisor.apm.payload is None


def test_mismatched_capture_manifest_hash_fails_closed(advisor):
    frame = pd.DataFrame([quote_row()])
    assert advisor.resolve_quote_from_dataframe(
        frame, 22400, "CE", expiry="13 OCT 26"
    ) is not None

    frame.loc[0, "contract_authority_manifest_sha256"] = "f" * 64
    assert advisor.resolve_quote_from_dataframe(
        frame, 22400, "CE", expiry="13 OCT 26"
    ) is None


def test_ordered_atr_gate_prevents_resolver_and_apm_entry(advisor, monkeypatch):
    def unexpected_resolution(*_args, **_kwargs):
        pytest.fail("vetoed candidate must not invoke option resolver")

    monkeypatch.setattr(advisor, "resolve_real_option_quote", unexpected_resolution)
    result = advisor.evaluate_entry_gates(
        entry_dir="CE",
        signal_display="BUY NIFTY 22400 CE @ Breakout",
        in_lunch_dead_zone=False,
        is_counter_trend_fade=False,
        can_enter_energy=True,
        e_atr_rem=100.0,
        req_energy=50.0,
        insufficient_displacement=False,
        atr_1m=15.0,
        atr_extension_exhausted=True,
        session_range=350.0,
        spread_ratio=0.01,
        chosen_strike=22400,
        contract_choice="NIFTY 22400 CE [ITM]",
        bar_close_cutoff_epoch=1728445860.0,
        spot_close=22441.2,
        bar_time_str="2026-10-09T09:46:00+05:30",
        sl_pts=30.0,
        target_pts=60.0,
        total_drag_pts=3.5,
        current_gear="GEAR_2_TREND",
        btime=dtime(9, 46),
    )

    assert result["risk_flag"] == "VETO_ATR_EXTENSION_EXHAUSTED"
    assert result["candidate_status"] == "NONE"
    assert advisor.apm.state == STATE_STANDBY


def test_audit_emission_restores_append_and_safety_contract(advisor):
    advisor.emit_and_append_audit_log({"timestamp": "2026-10-09T09:46:00+05:30", "risk_flag": "NORMAL"})

    row = json.loads(advisor.audit_log_path.read_text(encoding="utf-8"))
    assert row["read_only"] is True
    assert row["is_order_action"] is False
    assert row["broker_api_called"] is False
    assert row["allowed_for_live_execution"] is False
    assert row["risk_flag"] == "NORMAL"

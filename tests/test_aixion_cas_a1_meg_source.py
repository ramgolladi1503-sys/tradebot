from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from aixion_trade_intelligence.cas_a1_meg_source import (
    CasA1MegSourceError,
    build_completed_bar_bundle,
)


IST = ZoneInfo("Asia/Kolkata")


def _identity():
    return {
        "index": {
            "instrument_key": "NSE_INDEX|Nifty 50",
            "symbol": "NIFTY 50",
            "instrument_token": "256265",
        },
        "constituents": [
            {
                "instrument_key": f"NSE_EQ|C{i:02d}",
                "symbol": f"C{i:02d}",
                "instrument_token": str(1000 + i),
            }
            for i in range(49)
        ],
    }


def _row(minute: str):
    ts = datetime(2026, 8, 18, 15, int(minute.split(":")[1]), tzinfo=IST)
    return {
        "schema_version": 1,
        "source_kind": "LIVE_CAPTURED_METADATA",
        "run_id": "meg-live-20260818",
        "session_date": "2026-08-18",
        "symbol": "NIFTY 50",
        "source": "kite",
        "export_timestamp_utc": ts.replace(minute=ts.minute + 1).astimezone(ZoneInfo("UTC")).isoformat(),
        "source_generated_at_epoch": ts.timestamp() + 60,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": True,
        "duplicate_interval": False,
        "missing_constituents": [],
        "stale_constituents": [],
        "duplicate_constituents": [],
        "misaligned_constituents": [],
        "late_constituents": [],
        "live_universe": {"index_instrument_token": 256265},
        "index_bar": {
            "symbol": "NIFTY 50",
            "instrument_token": 256265,
            "ts": ts.isoformat(),
            "open": 25000.0,
            "high": 25002.0,
            "low": 24999.0,
            "close": 25001.0 if minute == "15:10" else 25005.0,
            "completed": True,
        },
        "constituent_bar_details": [
            {
                "symbol": f"C{i:02d}",
                "instrument_token": 1000 + i,
                "ts": ts.isoformat(),
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.1 + i + (0.1 if minute == "15:14" else 0.0),
                "completed": True,
            }
            for i in range(49)
        ],
    }


def test_builds_exact_49_constituent_two_minute_bundle_plus_nifty_1514():
    bundle = build_completed_bar_bundle(
        captured_metadata_rows=[_row("15:10"), _row("15:14")],
        identity_contract=_identity(),
        session_date="2026-08-18",
    )
    assert bundle["evidence_kind"] == "CAS_A1_MEG_COMPLETED_BAR_BUNDLE"
    assert bundle["constituent_count"] == 49
    assert len(bundle["completed_minute_bars"]) == 99
    assert bundle["source_provider"] == "KITE"
    assert bundle["tick_to_minute_inference_authorized"] is False
    assert bundle["broker_write_authority"] is False
    assert bundle["order_authority"] is False
    keys = {(row["instrument_key"], row["minute"]) for row in bundle["completed_minute_bars"]}
    assert ("NSE_EQ|C00", "15:10") in keys
    assert ("NSE_EQ|C48", "15:14") in keys
    assert ("NSE_INDEX|Nifty 50", "15:14") in keys


def test_missing_constituent_bar_fails_closed():
    rows = [_row("15:10"), _row("15:14")]
    rows[1]["constituent_bar_details"] = rows[1]["constituent_bar_details"][:-1]
    with pytest.raises(CasA1MegSourceError, match="missing CAS-A1 MEG constituent bars"):
        build_completed_bar_bundle(
            captured_metadata_rows=rows,
            identity_contract=_identity(),
            session_date="2026-08-18",
        )


def test_wrong_constituent_token_fails_identity_binding():
    rows = [_row("15:10"), _row("15:14")]
    rows[0]["constituent_bar_details"][0]["instrument_token"] = 999999
    with pytest.raises(CasA1MegSourceError, match="constituent token mismatch"):
        build_completed_bar_bundle(
            captured_metadata_rows=rows,
            identity_contract=_identity(),
            session_date="2026-08-18",
        )


def test_non_live_or_replay_metadata_is_rejected():
    rows = [_row("15:10"), _row("15:14")]
    rows[0]["source_kind"] = "REPLAY_FIXTURE"
    with pytest.raises(CasA1MegSourceError, match="unsafe or non-live MEG metadata"):
        build_completed_bar_bundle(
            captured_metadata_rows=rows,
            identity_contract=_identity(),
            session_date="2026-08-18",
        )


def test_any_meg_completeness_issue_fails_closed():
    rows = [_row("15:10"), _row("15:14")]
    rows[1]["stale_constituents"] = ["C17"]
    with pytest.raises(CasA1MegSourceError, match="stale_constituents"):
        build_completed_bar_bundle(
            captured_metadata_rows=rows,
            identity_contract=_identity(),
            session_date="2026-08-18",
        )


def test_cross_session_completed_bar_is_rejected():
    rows = [_row("15:10"), _row("15:14")]
    bad = deepcopy(rows[0])
    bad["constituent_bar_details"][0]["ts"] = "2026-08-17T15:10:00+05:30"
    rows[0] = bad
    with pytest.raises(CasA1MegSourceError, match="cross-session"):
        build_completed_bar_bundle(
            captured_metadata_rows=rows,
            identity_contract=_identity(),
            session_date="2026-08-18",
        )

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from aixion_trade_intelligence.cas_a1 import FROZEN_SPEC_PAYLOAD, FROZEN_SPEC_SHA256
from aixion_trade_intelligence.cas_a1_source_adapter import (
    CasA1SourceAdapterError,
    build_cas_a1_observation_payload,
)


def _constituents():
    return [f"NSE_EQ|C{i:02d}" for i in range(49)]


def _ts(hour: int, minute: int, second: int = 0):
    local = datetime(2026, 8, 18, hour, minute, second, tzinfo=ZoneInfo("Asia/Kolkata"))
    return local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _bundle():
    constituents = _constituents()
    bars = []
    for i, instrument in enumerate(constituents):
        bars.append({
            "instrument_key": instrument,
            "minute": "15:10",
            "close": 100.0 + i,
            "available_time": _ts(15, 11),
            "source_event_id": f"{instrument}-1510",
            "source_provider": "KITE_READ_ONLY",
            "bar_complete": True,
        })
        bars.append({
            "instrument_key": instrument,
            "minute": "15:14",
            "close": 100.1 + i,
            "available_time": _ts(15, 15),
            "source_event_id": f"{instrument}-1514",
            "source_provider": "KITE_READ_ONLY",
            "bar_complete": True,
        })
    bars.append({
        "instrument_key": "NSE_INDEX|Nifty 50",
        "minute": "15:14",
        "close": 25000.0,
        "available_time": _ts(15, 15),
        "source_event_id": "nifty-1514",
        "source_provider": "KITE_READ_ONLY",
        "bar_complete": True,
    })
    return {
        "session_id": "2026-08-18",
        "session_date": "2026-08-18",
        "index_instrument": "NSE_INDEX|Nifty 50",
        "futures_instrument": "NSE_FO|NIFTY_AUG_FUT",
        "analytics_contract": {
            "cas_a1": {
                "enabled": True,
                **FROZEN_SPEC_PAYLOAD,
                "spec_sha256": FROZEN_SPEC_SHA256,
                "frozen_constituents": constituents,
            }
        },
        "completed_minute_bars": bars,
        "point_marks": [
            {
                "instrument_key": "NSE_INDEX|Nifty 50",
                "label": "FINAL_CAS",
                "price": 25075.0,
                "available_time": _ts(15, 29, 2),
                "source_event_id": "cas-final",
                "source_provider": "KITE_READ_ONLY",
            },
            {
                "instrument_key": "NSE_FO|NIFTY_AUG_FUT",
                "label": "15:29",
                "price": 25040.0,
                "available_time": _ts(15, 29, 3),
                "source_event_id": "fut-1529",
                "source_provider": "KITE_READ_ONLY",
            },
            {
                "instrument_key": "NSE_FO|NIFTY_AUG_FUT",
                "label": "15:39",
                "price": 25050.0,
                "available_time": _ts(15, 39, 2),
                "source_event_id": "fut-1539",
                "source_provider": "KITE_READ_ONLY",
            },
        ],
    }


def test_adapter_preserves_exact_completed_minute_semantics():
    payload = build_cas_a1_observation_payload(_bundle())
    assert len(payload["constituent_marks"]) == 49
    assert payload["nifty_1514"] == 25000.0
    assert payload["final_cas_index"] == 25075.0
    assert payload["future_1529"] == 25040.0
    assert payload["future_1539"] == 25050.0
    assert payload["source_provider"] == "KITE_READ_ONLY"
    assert payload["adapter_contract"]["completed_minute_close_semantics"] is True
    assert payload["adapter_contract"]["tick_to_minute_inference_authorized"] is False
    assert payload["adapter_contract"]["forward_fill_authorized"] is False
    assert payload["adapter_contract"]["instrument_substitution_authorized"] is False
    assert payload["adapter_contract"]["timestamp_shift_authorized"] is False


def test_missing_constituent_minute_fails_closed_not_forward_filled():
    bundle = _bundle()
    bundle["completed_minute_bars"] = [
        row for row in bundle["completed_minute_bars"]
        if not (row["instrument_key"] == "NSE_EQ|C00" and row["minute"] == "15:10")
    ]
    with pytest.raises(CasA1SourceAdapterError, match="missing exact completed-minute evidence"):
        build_cas_a1_observation_payload(bundle)


def test_incomplete_bar_is_rejected_even_when_close_exists():
    bundle = _bundle()
    bundle["completed_minute_bars"][0]["bar_complete"] = False
    with pytest.raises(CasA1SourceAdapterError, match="incomplete minute bar rejected"):
        build_cas_a1_observation_payload(bundle)


def test_duplicate_bar_is_rejected_as_ambiguous():
    bundle = _bundle()
    bundle["completed_minute_bars"].append(deepcopy(bundle["completed_minute_bars"][0]))
    with pytest.raises(CasA1SourceAdapterError, match="duplicate completed minute bar"):
        build_cas_a1_observation_payload(bundle)


def test_mixed_provider_evidence_is_rejected():
    bundle = _bundle()
    bundle["point_marks"][0]["source_provider"] = "OTHER_PROVIDER"
    with pytest.raises(CasA1SourceAdapterError, match="mixed source providers rejected"):
        build_cas_a1_observation_payload(bundle)


def test_cross_session_evidence_is_rejected():
    bundle = _bundle()
    bundle["point_marks"][2]["available_time"] = "2026-08-19T10:09:02Z"
    with pytest.raises(CasA1SourceAdapterError, match="cross-session evidence rejected"):
        build_cas_a1_observation_payload(bundle)

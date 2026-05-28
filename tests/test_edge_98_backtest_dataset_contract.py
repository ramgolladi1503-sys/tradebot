from __future__ import annotations

import json

import pytest

from core.backtest_dataset_contract import (
    HISTORICAL_DATASET_SCHEMA_VERSION,
    HISTORICAL_DATASET_SOURCE,
    NON_EXECUTABLE_MISSING_QUOTE_TIMESTAMP,
    NON_EXECUTABLE_STALE_QUOTE_TIMESTAMP,
    HistoricalDatasetContractError,
    build_historical_market_snapshot,
)


def _option_payload(**overrides: object) -> dict:
    payload = {
        "instrument_id": "NIFTY-2026-05-28-23000-CE",
        "symbol": "NIFTY",
        "instrument_type": "OPTION",
        "quote_timestamp": "2026-05-28T09:15:30+05:30",
        "expiry": "2026-05-28",
        "strike": 23000,
        "option_type": "CE",
        "bid": 101.5,
        "ask": 102.0,
        "ltp": 101.75,
        "volume": 1200,
        "oi": 25000,
        "metadata": {"segment": "NFO"},
    }
    payload.update(overrides)
    return payload


def _snapshot_payload(*instruments: dict, snapshot_timestamp: str = "2026-05-28T09:16:00+05:30") -> dict:
    return {
        "snapshot_timestamp": snapshot_timestamp,
        "market_session": "OPEN",
        "source_metadata": {"vendor": "fixture"},
        "instruments": list(instruments) or [_option_payload()],
    }


def test_historical_snapshot_is_deterministic_and_json_serializable() -> None:
    report = build_historical_market_snapshot(_snapshot_payload())

    assert report.schema_version == HISTORICAL_DATASET_SCHEMA_VERSION
    assert report.source == HISTORICAL_DATASET_SOURCE
    assert report.instrument_count == 1
    assert report.executable_instrument_count == 1
    assert report.non_executable_instrument_count == 0

    payload = report.to_payload()
    assert payload["snapshot_timestamp"] == "2026-05-28T03:46:00Z"
    assert payload["instruments"][0]["quote_timestamp"] == "2026-05-28T03:45:30Z"
    assert payload["instruments"][0]["executable"] is True
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["metadata"]["historical_dataset_contract"] is True

    encoded = json.dumps(payload, sort_keys=True)
    assert "NIFTY-2026-05-28-23000-CE" in encoded


def test_snapshot_timestamp_is_required_and_must_be_valid() -> None:
    payload = _snapshot_payload()
    payload.pop("snapshot_timestamp")

    with pytest.raises(HistoricalDatasetContractError, match="snapshot_timestamp is required"):
        build_historical_market_snapshot(payload)

    with pytest.raises(HistoricalDatasetContractError, match="snapshot_timestamp must be ISO-8601"):
        build_historical_market_snapshot(_snapshot_payload(snapshot_timestamp="not-a-time"))


def test_missing_option_fields_fail_closed() -> None:
    payload = _option_payload()
    payload.pop("expiry")

    with pytest.raises(HistoricalDatasetContractError, match="missing required option fields: expiry"):
        build_historical_market_snapshot(_snapshot_payload(payload))


def test_negative_market_values_are_rejected() -> None:
    for field_name in ("bid", "ask", "ltp", "volume", "oi"):
        payload = _option_payload(**{field_name: -1})

        with pytest.raises(HistoricalDatasetContractError, match=f"{field_name} must be non-negative"):
            build_historical_market_snapshot(_snapshot_payload(payload))


def test_ask_below_bid_is_rejected() -> None:
    payload = _option_payload(bid=102.0, ask=101.95)

    with pytest.raises(HistoricalDatasetContractError, match="ask must be greater than or equal to bid"):
        build_historical_market_snapshot(_snapshot_payload(payload))


def test_missing_quote_timestamp_is_non_executable_not_silently_executable() -> None:
    payload = _option_payload(quote_timestamp=None)

    snapshot = build_historical_market_snapshot(_snapshot_payload(payload))

    instrument = snapshot.instruments[0]
    assert instrument.executable is False
    assert instrument.non_executable_reasons == (NON_EXECUTABLE_MISSING_QUOTE_TIMESTAMP,)
    assert snapshot.executable_instrument_count == 0
    assert snapshot.non_executable_instrument_count == 1


def test_stale_quote_timestamp_is_non_executable() -> None:
    payload = _option_payload(quote_timestamp="2026-05-28T09:10:00+05:30")

    snapshot = build_historical_market_snapshot(_snapshot_payload(payload), max_quote_age_seconds=60)

    instrument = snapshot.instruments[0]
    assert instrument.executable is False
    assert instrument.non_executable_reasons == (NON_EXECUTABLE_STALE_QUOTE_TIMESTAMP,)


def test_multiple_instruments_are_supported_and_sorted_deterministically() -> None:
    late = _option_payload(instrument_id="z-late", symbol="BANKNIFTY")
    early = _option_payload(instrument_id="a-early", symbol="NIFTY", option_type="PE")

    snapshot = build_historical_market_snapshot(_snapshot_payload(late, early))

    assert snapshot.instrument_count == 2
    assert [instrument.instrument_id for instrument in snapshot.instruments] == ["a-early", "z-late"]
    assert snapshot.executable_instrument_count == 2

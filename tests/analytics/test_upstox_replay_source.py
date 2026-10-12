from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core.analytics.upstox_replay_source import OfflineOptionOHLCManifest, ReplaySourceError


IST = ZoneInfo("Asia/Kolkata")
SESSION = "2026-10-12"
CONTRACT = {"underlying": "NIFTY", "expiry": "2026-10-29", "strike": 25000, "option_type": "CE"}


def _ts(minute: int) -> int:
    return int(datetime(2026, 10, 12, 9, minute, tzinfo=IST).timestamp() * 1000)


def _write_source(tmp_path: Path, rows: list[dict] | None = None, *, interval="1minute"):
    if rows is None:
        rows = [
            {"timestamp": "2026-10-12T09:15:00+05:30", "open": 100, "high": 102, "low": 99, "close": 101},
            {"timestamp": "2026-10-12T09:16:00+05:30", "open": 101, "high": 103, "low": 100, "close": 102},
        ]
    source = tmp_path / "option.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close"])
        writer.writeheader()
        writer.writerows(rows)
    raw = source.read_bytes()
    master = tmp_path / "instrument_master.csv"
    with master.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["instrument_token", "underlying", "expiry", "strike", "option_type"])
        writer.writeheader()
        writer.writerow({"instrument_token": "12345", **CONTRACT})
    master_raw = master.read_bytes()
    manifest = {
        "schema_version": 1,
        "dataset_id": "capture-2026-10-12-nifty-25000ce",
        "provider": "upstox",
        "session_date": SESSION,
        "interval": interval,
        "timezone": "Asia/Kolkata",
        "timestamp_semantics": "interval_start",
        "instrument_master": {
            "path": "instrument_master.csv",
            "format": "csv",
            "size_bytes": len(master_raw),
            "sha256": hashlib.sha256(master_raw).hexdigest(),
        },
        "entries": [{
            "contract": CONTRACT,
            "instrument_token": "12345",
            "path": "option.csv",
            "format": "csv",
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, manifest, source


def _event(**changes):
    return {
        "event_id": "evt-replay-test",
        "ts_epoch_ms": _ts(15),
        "trade_key": "NIFTY|2026-10-29|25000|CE|BUY",
        "ts_epoch_ms": _ts(15),
        "symbol": "NIFTY",
        "expiry": "2026-10-29",
        "strike": 25000,
        "option_type": "CE",
        "instrument_token": "12345",
        "side": "BUY",
        **changes,
    }


def test_manifest_loader_checks_hash_contract_interval_and_returns_observed_ohlc(tmp_path):
    manifest_path, _, _ = _write_source(tmp_path)
    loader = OfflineOptionOHLCManifest(manifest_path)
    rows, source = loader(_event(), _ts(15), _ts(17), "1minute")
    assert source == "upstox_manifest:capture-2026-10-12-nifty-25000ce"
    assert [(row["time_ms"], row["high"], row["low"]) for row in rows] == [
        (_ts(15), 102.0, 99.0), (_ts(16), 103.0, 100.0)
    ]
    assert loader.provenance["file_sha256"] == loader.manifest["entries"][0]["sha256"]
    assert loader.provenance["contract"] == CONTRACT
    assert loader.provenance["instrument_token"] == "12345"
    assert loader.provenance["source_authenticity_verified"] is False


def test_manifest_and_data_hashes_bind_the_exact_parsed_snapshots(tmp_path, monkeypatch):
    from core.analytics import upstox_replay_source as source_module

    manifest_path, _, source = _write_source(tmp_path)
    expected_source_bytes = source.read_bytes()
    real_parse = source_module._read_rows
    observed = {}

    def mutate_after_snapshot(payload, file_format):
        observed["parsed_sha256"] = hashlib.sha256(payload).hexdigest()
        source.write_text("timestamp,open,high,low,close\n", encoding="utf-8")
        return real_parse(payload, file_format)

    monkeypatch.setattr(source_module, "_read_rows", mutate_after_snapshot)
    loader = OfflineOptionOHLCManifest(manifest_path)
    rows, _ = loader(_event(), _ts(15), _ts(17), "1minute")

    assert observed["parsed_sha256"] == hashlib.sha256(expected_source_bytes).hexdigest()
    assert loader.provenance["file_sha256"] == observed["parsed_sha256"]
    assert len(rows) == 2


def test_manifest_loader_can_bind_candidate_contract_without_event_token(tmp_path):
    manifest_path, _, _ = _write_source(tmp_path)
    loader = OfflineOptionOHLCManifest(manifest_path)
    event = _event()
    event.pop("instrument_token")

    rows, _ = loader(event, _ts(15), _ts(17), "1minute")

    assert len(rows) == 2
    assert loader.provenance["event_token_bound"] is False
    assert loader.provenance["identity_binding_mode"] == "STRUCTURED_CONTRACT_AND_HASHED_OPERATOR_MASTER"


@pytest.mark.parametrize(
    ("event_changes", "end_ms", "interval", "message"),
    [
        ({"strike": 25100}, _ts(17), "1minute", "exact_contract_entry_not_unique"),
        ({}, _ts(17), "5minute", "interval_mismatch"),
        ({"expiry": None}, _ts(17), "1minute", "exact_option_identity_required"),
        ({"instrument_token": "99999"}, _ts(17), "1minute", "exact_contract_entry_not_unique"),
        ({"side": None}, _ts(17), "1minute", "trade_side_required"),
        ({}, _ts(18), "1minute", "truncated_or_gapped_source_window"),
    ],
)
def test_manifest_loader_fails_closed_on_contract_interval_or_coverage(
    tmp_path, event_changes, end_ms, interval, message
):
    manifest_path, _, _ = _write_source(tmp_path)
    loader = OfflineOptionOHLCManifest(manifest_path)
    with pytest.raises(ReplaySourceError, match=message):
        loader(_event(**event_changes), _ts(15), end_ms, interval)


@pytest.mark.parametrize("mutation", ["duplicate", "gap"])
def test_manifest_loader_rejects_duplicate_and_gap_rows(tmp_path, mutation):
    rows = [
        {"timestamp": "2026-10-12T09:15:00+05:30", "open": 100, "high": 102, "low": 99, "close": 101},
        {"timestamp": "2026-10-12T09:16:00+05:30", "open": 101, "high": 103, "low": 100, "close": 102},
    ]
    if mutation == "duplicate":
        rows.append(dict(rows[-1]))
    else:
        rows[1]["timestamp"] = "2026-10-12T09:17:00+05:30"
    manifest_path, _, _ = _write_source(tmp_path, rows)
    loader = OfflineOptionOHLCManifest(manifest_path)
    with pytest.raises(ReplaySourceError, match="duplicate_source_timestamp|truncated_or_gapped_source_window"):
        loader(_event(), _ts(15), _ts(17), "1minute")


def test_manifest_loader_checks_file_size_and_digest_before_read(tmp_path):
    manifest_path, _, source = _write_source(tmp_path)
    source.write_text(source.read_text() + "\n", encoding="utf-8")
    loader = OfflineOptionOHLCManifest(manifest_path)
    with pytest.raises(ReplaySourceError, match="source_size_mismatch"):
        loader(_event(), _ts(15), _ts(17), "1minute")


def test_manifest_loader_rejects_session_mismatch(tmp_path):
    manifest_path, manifest, _ = _write_source(tmp_path)
    manifest["session_date"] = "2026-10-09"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    loader = OfflineOptionOHLCManifest(manifest_path)
    with pytest.raises(ReplaySourceError, match="event_session_mismatch"):
        loader(_event(), _ts(15), _ts(17), "1minute")


def test_manifest_loader_does_not_round_subminute_events_back_to_prior_bar(tmp_path):
    manifest_path, _, _ = _write_source(tmp_path)
    loader = OfflineOptionOHLCManifest(manifest_path)
    subminute_event = _ts(15) + 30_000
    with pytest.raises(ReplaySourceError, match="event_not_on_source_bar_boundary"):
        loader(_event(ts_epoch_ms=subminute_event), subminute_event, subminute_event + 120_000, "1minute")


def test_manifest_loader_requires_instrument_master_contract_binding(tmp_path):
    manifest_path, manifest, _ = _write_source(tmp_path)
    master_path = tmp_path / "instrument_master.csv"
    master_path.write_text(
        "instrument_token,underlying,expiry,strike,option_type\n12345,NIFTY,2026-10-29,25000,PE\n",
        encoding="utf-8",
    )
    raw = master_path.read_bytes()
    manifest["instrument_master"].update(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReplaySourceError, match="manifest_contract_not_bound_by_instrument_master"):
        OfflineOptionOHLCManifest(manifest_path)


@pytest.mark.parametrize("timestamp", ["2026-10-12T09:14:00+05:30", "2026-10-12T15:30:00+05:30"])
def test_manifest_loader_rejects_preopen_and_close_exclusive_source_rows(tmp_path, timestamp):
    rows = [
        {"timestamp": timestamp, "open": 100, "high": 102, "low": 99, "close": 101},
        {"timestamp": "2026-10-12T09:16:00+05:30", "open": 101, "high": 103, "low": 100, "close": 102},
    ]
    manifest_path, _, _ = _write_source(tmp_path, rows)
    loader = OfflineOptionOHLCManifest(manifest_path)
    with pytest.raises(ReplaySourceError, match="source_row_outside_market_session"):
        loader(_event(), _ts(15), _ts(17), "1minute")


def test_manifest_loader_requires_source_and_event_timestamp_binding(tmp_path):
    manifest_path, _, _ = _write_source(tmp_path)
    loader = OfflineOptionOHLCManifest(manifest_path)
    with pytest.raises(ReplaySourceError, match="event_timestamp_binding_mismatch"):
        loader(_event(ts_epoch_ms=_ts(16)), _ts(15), _ts(17), "1minute")


def test_manifest_loader_rejects_non_exchange_timezone(tmp_path):
    manifest_path, manifest, _ = _write_source(tmp_path)
    manifest["timezone"] = "UTC"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReplaySourceError, match="unsupported_exchange_timezone"):
        OfflineOptionOHLCManifest(manifest_path)


def test_source_interval_grid_uses_configured_nondefault_open(tmp_path, monkeypatch):
    from core.analytics import upstox_replay_source as source_module

    monkeypatch.setattr(source_module.cfg, "MARKET_OPEN_IST", "09:30")
    ts_930 = int(datetime(2026, 10, 12, 9, 30, tzinfo=IST).timestamp() * 1000)
    ts_932 = int(datetime(2026, 10, 12, 9, 32, tzinfo=IST).timestamp() * 1000)
    ts_931 = int(datetime(2026, 10, 12, 9, 31, tzinfo=IST).timestamp() * 1000)

    assert source_module._ts_grid_origin(ts_930, IST, "2minute") == 0
    assert source_module._ts_grid_origin(ts_932, IST, "2minute") == 0
    assert source_module._ts_grid_origin(ts_931, IST, "2minute") != 0


@pytest.mark.parametrize("start_minute", [14, 30])
def test_manifest_loader_rejects_event_window_outside_configured_market_hours(tmp_path, start_minute):
    manifest_path, _, _ = _write_source(tmp_path)
    loader = OfflineOptionOHLCManifest(manifest_path)
    if start_minute == 14:
        start = _ts(15) - 60_000
    else:
        start = int(datetime(2026, 10, 12, 15, 30, tzinfo=IST).timestamp() * 1000)
    with pytest.raises(ReplaySourceError, match="event_window_outside_market_session"):
        loader(_event(ts_epoch_ms=start), start, start + 60_000, "1minute")

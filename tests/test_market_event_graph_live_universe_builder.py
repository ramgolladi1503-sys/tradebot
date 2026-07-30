import csv
import json
from pathlib import Path

import pytest

from scripts.build_market_event_graph_live_universe_v1 import (
    BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE,
    BLOCKED_BY_BROKER_INSTRUMENT_CROSSWALK,
    BROKER_TOKEN_DOMAIN_MISMATCH,
    build_contract,
    crosswalk_constituents,
    load_broker_instruments,
    parse_official_constituents,
)
from core.market_event_graph_live_runtime_bridge import canonical_live_universe_sha256


def _official_csv(symbols):
    rows = [
        {
            "Company Name": f"Company {symbol}",
            "Industry": "Financial Services",
            "Symbol": symbol,
            "Series": "EQ",
            "ISIN Code": f"INE{idx:09d}",
        }
        for idx, symbol in enumerate(symbols)
    ]
    out = ["Company Name,Industry,Symbol,Series,ISIN Code"]
    out.extend(",".join(row[field] for field in ("Company Name", "Industry", "Symbol", "Series", "ISIN Code")) for row in rows)
    return "\n".join(out).encode("utf-8")


def _symbols():
    return [f"NIFTY{i:02d}" for i in range(50)]


def _instrument_rows(symbols):
    rows = [
        {
            "tradingsymbol": symbol,
            "exchange": "NSE",
            "instrument_type": "EQ",
            "series": "EQ",
            "instrument_token": str(1000 + idx),
        }
        for idx, symbol in enumerate(symbols)
    ]
    rows.append(
        {
            "tradingsymbol": "NIFTY 50",
            "exchange": "NSE",
            "instrument_type": "INDEX",
            "instrument_token": "256265",
        }
    )
    return rows


def test_authoritative_csv_requires_exactly_fifty_unique_eq_symbols():
    constituents, report = parse_official_constituents(_official_csv(_symbols()))

    assert report["row_count"] == 50
    assert report["unique_symbol_count"] == 50
    assert report["duplicate_symbols"] == []
    assert constituents[0].symbol == "NIFTY00"
    assert constituents[-1].series == "EQ"


def test_authoritative_csv_blocks_duplicates_and_non_eq_series():
    raw = _official_csv(_symbols()[:-1]).decode("utf-8") + "\nCompany X,Tech,NIFTY00,BE,INEX"

    with pytest.raises(ValueError) as exc:
        parse_official_constituents(raw.encode("utf-8"))

    assert BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE in str(exc.value)
    assert "NIFTY00" in str(exc.value)


def test_broker_crosswalk_requires_unique_cash_equity_and_index_mapping():
    constituents, _ = parse_official_constituents(_official_csv(_symbols()))
    summary, index_mapping, rows = crosswalk_constituents(
        constituents,
        _instrument_rows(_symbols()),
        broker_provider="kite",
        index_symbol="NIFTY",
    )

    assert summary["uniquely_mapped_count"] == 50
    assert summary["missing_count"] == 0
    assert summary["index_mapping_status"] == "MAPPED"
    assert index_mapping["instrument_token"] == 256265
    assert rows[0]["mapping_status"] == "MAPPED"


def test_broker_crosswalk_blocks_missing_or_ambiguous_rows():
    constituents, _ = parse_official_constituents(_official_csv(_symbols()))
    instruments = _instrument_rows(_symbols()[1:])
    instruments.append({"tradingsymbol": "NIFTY00", "exchange": "NSE", "instrument_type": "FUT", "instrument_token": "77"})
    summary, index_mapping, rows = crosswalk_constituents(constituents, instruments, broker_provider="kite", index_symbol="NIFTY")

    assert summary["uniquely_mapped_count"] == 49
    assert summary["missing_count"] == 1
    assert index_mapping["mapping_status"] == "MAPPED"
    assert rows[0]["mapping_status"] == "MISSING"
    assert BLOCKED_BY_BROKER_INSTRUMENT_CROSSWALK == "BLOCKED_BY_BROKER_INSTRUMENT_CROSSWALK"


def test_contract_hash_excludes_capture_session_id_and_matches_bridge_validator(tmp_path):
    constituents, parse_report = parse_official_constituents(_official_csv(_symbols()))
    summary, index_mapping, rows = crosswalk_constituents(constituents, _instrument_rows(_symbols()), broker_provider="kite", index_symbol="NIFTY")
    official = {
        "raw_sha256": "a" * 64,
        "retrieved_at_utc": "2026-07-30T03:30:53Z",
        "retrieved_at_ist": "2026-07-30T09:00:53+05:30",
        "http_metadata": {"last_modified": "Thu, 30 Jul 2026 03:30:53 GMT"},
        "source_url": "file:nifty.csv",
        "raw_path": str(tmp_path / "nifty.csv"),
    }
    contract = build_contract(
        official=official,
        parse_report=parse_report,
        mapping_summary=summary,
        index_mapping=index_mapping,
        mapping_rows=rows,
        broker_provider="kite",
        broker_master_path=tmp_path / "instruments.csv",
        broker_master_sha256="b" * 64,
    )
    mutated = dict(contract)
    mutated["capture_session_id"] = "runtime-feed-session"

    assert canonical_live_universe_sha256(contract) == contract["canonical_sha256"]
    assert canonical_live_universe_sha256(mutated) == contract["canonical_sha256"]


def test_provider_domain_mismatch_is_exposed_for_upstox_contract(tmp_path):
    constituents, parse_report = parse_official_constituents(_official_csv(_symbols()))
    summary, index_mapping, rows = crosswalk_constituents(
        constituents,
        _instrument_rows(_symbols()),
        broker_provider="upstox",
        index_symbol="NIFTY",
    )
    official = {
        "raw_sha256": "a" * 64,
        "retrieved_at_utc": "2026-07-30T03:30:53Z",
        "retrieved_at_ist": "2026-07-30T09:00:53+05:30",
        "http_metadata": {"last_modified": "Thu, 30 Jul 2026 03:30:53 GMT"},
        "source_url": "file:nifty.csv",
        "raw_path": str(tmp_path / "nifty.csv"),
    }
    contract = build_contract(
        broker_provider="upstox",
        official=official,
        parse_report=parse_report,
        mapping_summary=summary,
        index_mapping=index_mapping,
        mapping_rows=rows,
        broker_master_path=tmp_path / "upstox_master.json",
        broker_master_sha256="b" * 64,
    )
    assert contract["token_domain"] == "upstox"
    assert contract["broker_provider"] == "upstox"
    assert contract["contract_filename"].startswith("nifty50_live_universe_upstox_")
    assert BROKER_TOKEN_DOMAIN_MISMATCH == "BROKER_TOKEN_DOMAIN_MISMATCH"


def test_load_broker_instruments_reads_csv_without_broker_session(tmp_path):
    path = tmp_path / "instruments.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["tradingsymbol", "exchange", "instrument_type", "instrument_token"])
        writer.writeheader()
        writer.writerow({"tradingsymbol": "NIFTY 50", "exchange": "NSE", "instrument_type": "INDEX", "instrument_token": "256265"})

    rows, digest = load_broker_instruments(Path(path))

    assert rows == [{"tradingsymbol": "NIFTY 50", "exchange": "NSE", "instrument_type": "INDEX", "instrument_token": "256265"}]
    assert digest

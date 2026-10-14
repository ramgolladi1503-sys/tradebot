"""Offline contract-master authority tests using schema-faithful synthetic bytes."""

import csv
import gzip
import hashlib
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core.nse_fo_contract_master import (
    EPOCH_1980,
    NSEContractMasterError,
    UPSTOX_INSTRUMENTS_URL,
    fetch_current_nse_fo_contract_master,
    load_verified_capture_authority,
    parse_nse_fo_contract_file,
    sha256_bytes,
    write_contract_authority_manifest,
)


NSE_COLUMNS = [
    "FinInstrmId", "UndrlygFinInstrmId", "FinInstrmNm", "TckrSymb", "XpryDt",
    "StrkPric", "OptnTp", "PrtdToTrad", "MinLot", "NewBrdLotQty", "DelFlg",
    "TradgStsNrmlMkt", "ElgbltyNrmlMkt",
]
SESSION_DATE = date(2026, 10, 13)
EXPIRY = date(2026, 10, 13)


def nse_row(*, instrument_id="12345", expiry=EXPIRY, strike_paise="2240000", option_type="CE", permitted="1", deleted="N", status="2", eligible="1"):
    epoch = int((datetime.combine(expiry, datetime.min.time(), tzinfo=timezone.utc) - EPOCH_1980).total_seconds())
    return {
        "FinInstrmId": instrument_id,
        "UndrlygFinInstrmId": "NIFTY",
        "FinInstrmNm": "OPTIDX",
        "TckrSymb": "NIFTY",
        "XpryDt": str(epoch),
        "StrkPric": strike_paise,
        "OptnTp": option_type,
        "PrtdToTrad": permitted,
        "MinLot": "1",
        "NewBrdLotQty": "1",
        "DelFlg": deleted,
        "TradgStsNrmlMkt": status,
        "ElgbltyNrmlMkt": eligible,
    }


def nse_payload(rows, columns=NSE_COLUMNS):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return gzip.compress(buffer.getvalue().encode("utf-8"))


def upstox_payload(*, key="NSE_FO|44598", symbol="NIFTY 22400 CE 13 OCT 26", strike=22400, expiry=EXPIRY):
    expiry_ms = int(datetime.combine(expiry, datetime.min.time(), tzinfo=ZoneInfo("Asia/Kolkata")).timestamp() * 1000)
    return json.dumps([{
        "instrument_key": key,
        "name": "NIFTY",
        "expiry": expiry_ms,
        "strike_price": strike,
        "instrument_type": "CE",
        "trading_symbol": symbol,
    }], separators=(",", ":")).encode("utf-8")


def test_parser_reads_expiry_paise_and_active_status_exactly():
    payload = nse_payload([nse_row()])

    master = parse_nse_fo_contract_file(
        payload,
        session_date=SESSION_DATE,
        trading_date=date(2026, 10, 9),
        source_url="https://nsearchives.nseindia.com/content/fo/NSE_FO_contract_09102026.csv.gz",
        file_name="NSE_FO_contract_09102026.csv.gz",
        downloaded_at_utc="2026-10-09T05:00:00+00:00",
        report_current_date=date(2026, 10, 9),
        report_future_date=SESSION_DATE,
    )

    assert master.nearest_expiry("NIFTY") == EXPIRY
    contract = master.exact_active_match("NIFTY", EXPIRY, 22400, "CE")
    assert contract is not None
    assert contract.instrument_id == "12345"
    assert contract.strike == 22400
    assert contract.permitted_to_trade is True
    assert contract.deleted is False
    assert contract.normal_market_trading_status == 2
    assert contract.normal_market_eligible is True
    assert master.sha256 == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("rows", [
    [nse_row(permitted="0")],
    [nse_row(deleted="Y")],
    [nse_row(eligible="0")],
    [nse_row(status="3")],
    [nse_row(status="1")],
    [nse_row(expiry=date(2026, 10, 12))],
])
def test_nontradable_deleted_or_expired_contract_is_not_active(rows):
    master = parse_nse_fo_contract_file(
        nse_payload(rows),
        session_date=SESSION_DATE,
        trading_date=date(2026, 10, 9),
        source_url="https://nsearchives.nseindia.com/content/fo/file.csv.gz",
        file_name="file.csv.gz",
        downloaded_at_utc="2026-10-09T05:00:00+00:00",
        report_current_date=date(2026, 10, 9),
        report_future_date=SESSION_DATE,
    )
    assert master.nearest_expiry("NIFTY") is None
    assert master.exact_active_match("NIFTY", EXPIRY, 22400, "CE") is None


def test_ambiguous_duplicate_nse_identity_fails_closed():
    master = parse_nse_fo_contract_file(
        nse_payload([nse_row(instrument_id="1"), nse_row(instrument_id="2")]),
        session_date=SESSION_DATE,
        trading_date=date(2026, 10, 9),
        source_url="https://nsearchives.nseindia.com/content/fo/file.csv.gz",
        file_name="file.csv.gz",
        downloaded_at_utc="2026-10-09T05:00:00+00:00",
        report_current_date=date(2026, 10, 9),
        report_future_date=SESSION_DATE,
    )
    assert master.exact_active_match("NIFTY", EXPIRY, 22400, "CE") is None


def test_missing_or_malformed_nse_schema_fails_closed():
    with pytest.raises(NSEContractMasterError, match="missing fields"):
        parse_nse_fo_contract_file(
            nse_payload([nse_row()], columns=["FinInstrmId", "TckrSymb"]),
            session_date=SESSION_DATE,
            trading_date=date(2026, 10, 9),
            source_url="https://nsearchives.nseindia.com/content/fo/file.csv.gz",
            file_name="file.csv.gz",
            downloaded_at_utc="2026-10-09T05:00:00+00:00",
            report_current_date=date(2026, 10, 9),
            report_future_date=SESSION_DATE,
        )
    with pytest.raises(NSEContractMasterError, match="valid gzip"):
        parse_nse_fo_contract_file(
            b"not-gzip",
            session_date=SESSION_DATE,
            trading_date=date(2026, 10, 9),
            source_url="https://nsearchives.nseindia.com/content/fo/file.csv.gz",
            file_name="file.csv.gz",
            downloaded_at_utc="2026-10-09T05:00:00+00:00",
            report_current_date=date(2026, 10, 9),
            report_future_date=SESSION_DATE,
        )


class FakeResponse:
    def __init__(self, *, content=b"", payload=None):
        self.content = content
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeNSESession:
    def __init__(self, payload, listing):
        self.payload = payload
        self.listing = listing
        self.response_listing_bytes = json.dumps(listing, separators=(",", ":")).encode()
        self.urls = []

    def get(self, url, **_kwargs):
        self.urls.append(url)
        if "all-reports-derivatives" in url:
            return FakeResponse()
        if "daily-reports" in url:
            return FakeResponse(content=self.response_listing_bytes, payload=self.listing)
        return FakeResponse(content=self.payload)


def test_fetch_uses_official_report_listing_and_persists_asof_metadata(tmp_path):
    payload = nse_payload([nse_row()])
    listing = {
        "currentDate": "09-Oct-2026",
        "futureDate": "13-Oct-2026",
        "CurrentDay": [{
            "fileKey": "NSE-FO-CONTRACT-CSV",
            "displayName": "F&O-MII Contract File (NSE Exclusive contract)",
            "tradingDate": "09-Oct-2026",
            "fileActlName": "NSE_FO_contract_09102026.csv.gz",
            "filePath": "https://nsearchives.nseindia.com/content/fo/",
        }],
    }
    fake_session = FakeNSESession(payload, listing)

    master, path, metadata = fetch_current_nse_fo_contract_master(
        SESSION_DATE, tmp_path, session=fake_session
    )

    assert path.read_bytes() == payload
    assert master.session_date == SESSION_DATE
    assert master.trading_date == date(2026, 10, 9)
    assert metadata["artifact_filename"] == "NSE_FO_contract_09102026.csv.gz"
    assert metadata["file_sha256"] == sha256_bytes(payload)
    assert metadata["requested_session_date"] == "2026-10-13"
    assert (tmp_path / metadata["listing_artifact_filename"]).read_bytes() == fake_session.response_listing_bytes
    assert metadata["listing_sha256"] == sha256_bytes(fake_session.response_listing_bytes)
    assert len(fake_session.urls) == 3


def test_fetch_rejects_session_not_named_by_current_or_future_nse_listing(tmp_path):
    listing = {
        "currentDate": "09-Oct-2026",
        "futureDate": "13-Oct-2026",
        "CurrentDay": [],
    }
    fake_session = FakeNSESession(b"", listing)

    with pytest.raises(NSEContractMasterError, match="not NSE current/future date"):
        fetch_current_nse_fo_contract_master(date(2026, 10, 12), tmp_path, session=fake_session)

    assert len(fake_session.urls) == 2


def _write_verified_fixture(
    data_dir: Path,
    *,
    symbol="NIFTY 22400 CE 13 OCT 26",
    selected_symbol=None,
    nse_rows=None,
):
    data_dir.mkdir(parents=True)
    nse_bytes = nse_payload(nse_rows or [nse_row()])
    upstox_bytes = gzip.compress(upstox_payload(symbol=symbol))
    nse_name = "NSE_FO_contract_09102026.csv.gz"
    upstox_name = "upstox_complete_20261013.json.gz"
    (data_dir / nse_name).write_bytes(nse_bytes)
    (data_dir / upstox_name).write_bytes(upstox_bytes)
    nse_metadata = {
        "artifact_filename": nse_name,
        "file_url": f"https://nsearchives.nseindia.com/content/fo/{nse_name}",
        "file_sha256": sha256_bytes(nse_bytes),
        "trading_date": "2026-10-09",
        "downloaded_at_utc": "2026-10-09T05:00:00+00:00",
        "report_current_date": "2026-10-09",
        "report_future_date": "2026-10-13",
        "requested_session_date": "2026-10-13",
        "schema_version": "NSE_MII_FO_CONTRACT_V1",
        "tls_verification": "requests_default_certificate_validation",
        "listing_artifact_filename": "nse_fo_reports_2026-10-13.json",
        "listing_source_url": "https://www.nseindia.com/api/daily-reports?key=FO",
    }
    listing = {
        "currentDate": "09-Oct-2026",
        "futureDate": "13-Oct-2026",
        "CurrentDay": [{
            "fileKey": "NSE-FO-CONTRACT-CSV",
            "displayName": "F&O-MII Contract File (NSE Exclusive contract)",
            "tradingDate": "09-Oct-2026",
            "fileActlName": nse_name,
            "filePath": "https://nsearchives.nseindia.com/content/fo/",
        }],
    }
    listing_bytes = json.dumps(listing, separators=(",", ":")).encode()
    (data_dir / "nse_fo_reports_2026-10-13.json").write_bytes(listing_bytes)
    nse_metadata["listing_sha256"] = sha256_bytes(listing_bytes)
    upstox_metadata = {
        "artifact_filename": upstox_name,
        "source_url": UPSTOX_INSTRUMENTS_URL,
        "sha256": sha256_bytes(upstox_bytes),
        "downloaded_at_utc": "2026-10-13T03:30:00+00:00",
        "tls_verification": "requests_default_certificate_validation",
        "live_identity_eligible": True,
    }
    selected = [{
        "contract_key": "NIFTY|2026-10-13|22400|CE",
        "underlying": "NIFTY",
        "expiry": "2026-10-13",
        "strike": "22400",
        "option_type": "CE",
        "nse_instrument_id": "12345",
        "nse_permitted_to_trade": True,
        "nse_deleted": False,
        "nse_normal_market_trading_status": 2,
        "nse_normal_market_eligible": True,
        "upstox_instrument_key": "NSE_FO|44598",
        "upstox_trading_symbol": selected_symbol or symbol,
    }]
    _, manifest_hash = write_contract_authority_manifest(
        data_dir,
        session_date=SESSION_DATE,
        nse_metadata=nse_metadata,
        upstox_metadata=upstox_metadata,
        selected_contracts=selected,
    )
    return manifest_hash


def test_manifest_rehashes_both_sources_and_verifies_exact_mapping(tmp_path):
    data_dir = tmp_path / SESSION_DATE.isoformat()
    expected_hash = _write_verified_fixture(data_dir)

    authority = load_verified_capture_authority(data_dir, expected_hash)

    assert authority.manifest_sha256 == expected_hash
    entry = authority.verify_candidate(
        instrument_key="NSE_FO|44598",
        symbol="NIFTY 22400 CE 13 OCT 26",
        underlying="NIFTY",
        expiry=EXPIRY,
        strike=22400,
        option_type="CE",
    )
    assert entry is not None
    assert authority.verify_candidate(
        instrument_key="NSE_FO|44598",
        symbol="NIFTY 22400 PE 13 OCT 26",
        underlying="NIFTY",
        expiry=EXPIRY,
        strike=22400,
        option_type="CE",
    ) is None


def test_manifest_or_source_hash_mismatch_fails_closed(tmp_path):
    data_dir = tmp_path / SESSION_DATE.isoformat()
    expected_hash = _write_verified_fixture(data_dir)
    with pytest.raises(NSEContractMasterError, match="manifest hash"):
        load_verified_capture_authority(data_dir, "0" * 64)

    (data_dir / "upstox_complete_20261013.json.gz").write_bytes(b"changed")
    with pytest.raises(NSEContractMasterError, match="Upstox master hash"):
        load_verified_capture_authority(data_dir, expected_hash)


def test_nse_listing_hash_or_selected_file_mismatch_fails_closed(tmp_path):
    data_dir = tmp_path / SESSION_DATE.isoformat()
    expected_hash = _write_verified_fixture(data_dir)
    listing_path = data_dir / "nse_fo_reports_2026-10-13.json"
    listing_path.write_text("{}", encoding="utf-8")
    with pytest.raises(NSEContractMasterError, match="listing"):
        load_verified_capture_authority(data_dir, expected_hash)


def test_empty_selected_mapping_is_not_labeled_verified(tmp_path):
    data_dir = tmp_path / SESSION_DATE.isoformat()
    data_dir.mkdir()
    nse_name = "NSE_FO_contract_09102026.csv.gz"
    upstox_name = "upstox_complete_20261013.json.gz"
    nse_bytes = nse_payload([nse_row()])
    upstox_bytes = gzip.compress(upstox_payload())
    (data_dir / nse_name).write_bytes(nse_bytes)
    (data_dir / upstox_name).write_bytes(upstox_bytes)
    listing_path = data_dir / "nse_fo_reports_2026-10-13.json"
    listing_bytes = json.dumps({"currentDate": "09-Oct-2026", "futureDate": "13-Oct-2026", "CurrentDay": [{
        "fileKey": "NSE-FO-CONTRACT-CSV", "displayName": "NSE Exclusive contract",
        "tradingDate": "09-Oct-2026", "fileActlName": nse_name,
        "filePath": "https://nsearchives.nseindia.com/content/fo/",
    }]}).encode()
    listing_path.write_bytes(listing_bytes)
    nse_meta = {
        "artifact_filename": nse_name, "file_url": f"https://nsearchives.nseindia.com/content/fo/{nse_name}",
        "file_sha256": sha256_bytes(nse_bytes), "trading_date": "2026-10-09",
        "downloaded_at_utc": "2026-10-09T05:00:00+00:00", "report_current_date": "2026-10-09",
        "report_future_date": "2026-10-13", "requested_session_date": "2026-10-13",
        "schema_version": "NSE_MII_FO_CONTRACT_V1", "tls_verification": "requests_default_certificate_validation",
        "listing_artifact_filename": listing_path.name,
        "listing_source_url": "https://www.nseindia.com/api/daily-reports?key=FO",
        "listing_sha256": sha256_bytes(listing_bytes),
    }
    upstox_meta = {
        "artifact_filename": upstox_name, "source_url": UPSTOX_INSTRUMENTS_URL,
        "sha256": sha256_bytes(upstox_bytes), "downloaded_at_utc": "2026-10-13T03:30:00+00:00",
        "tls_verification": "requests_default_certificate_validation", "live_identity_eligible": True,
    }
    manifest_path, manifest_hash = write_contract_authority_manifest(
        data_dir, session_date=SESSION_DATE, nse_metadata=nse_meta, upstox_metadata=upstox_meta,
        selected_contracts=[],
    )
    assert json.loads(manifest_path.read_text())["status"] == "SOURCE_VERIFIED_NO_ELIGIBLE_MAPPINGS"
    with pytest.raises(NSEContractMasterError, match="not verified"):
        load_verified_capture_authority(data_dir, manifest_hash)


def test_upstox_symbol_mismatch_in_manifest_mapping_fails_closed(tmp_path):
    data_dir = tmp_path / SESSION_DATE.isoformat()
    expected_hash = _write_verified_fixture(
        data_dir,
        symbol="NIFTY 22400 CE 13 OCT 26",
        selected_symbol="WRONG 22400 CE 13 OCT 26",
    )

    with pytest.raises(NSEContractMasterError, match="uniquely match"):
        load_verified_capture_authority(data_dir, expected_hash)

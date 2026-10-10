"""NSE F&O contract-master acquisition, identity matching, and evidence checks.

The NSE report listing determines which dated NSE-exclusive MII contract file is
current for a session. Option expiry is read from that file, never generated from
a weekday or holiday heuristic. Raw source artifacts and a content-hashed manifest
are retained beside the market capture so later candidate audits can re-verify them.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests


NSE_REPORTS_PAGE = "https://www.nseindia.com/all-reports-derivatives"
NSE_FO_REPORTS_API = "https://www.nseindia.com/api/daily-reports?key=FO"
NSE_CONTRACT_FILE_KEY = "NSE-FO-CONTRACT-CSV"
NSE_CONTRACT_DISPLAY_MARKER = "NSE Exclusive contract"
NSE_CONTRACT_SCHEMA_VERSION = "NSE_MII_FO_CONTRACT_V1"
UPSTOX_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
AUTHORITY_MANIFEST_NAME = "contract_authority_manifest.json"
EPOCH_1980 = datetime(1980, 1, 1, tzinfo=timezone.utc)

NSE_REQUIRED_COLUMNS = {
    "FinInstrmId",
    "FinInstrmNm",
    "TckrSymb",
    "XpryDt",
    "StrkPric",
    "OptnTp",
    "PrtdToTrad",
    "DelFlg",
    "TradgStsNrmlMkt",
    "ElgbltyNrmlMkt",
}
UPSTOX_REQUIRED_FIELDS = {
    "instrument_key",
    "name",
    "expiry",
    "strike_price",
    "instrument_type",
    "trading_symbol",
}


class NSEContractMasterError(ValueError):
    """Raised when official contract evidence is unavailable or invalid."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _parse_report_date(value: Any) -> date:
    text = str(value or "").strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise NSEContractMasterError(f"Invalid NSE report date: {text!r}")


def _safe_basename(value: Any) -> str:
    name = str(value or "").strip()
    if not name or Path(name).name != name or name in {".", ".."}:
        raise NSEContractMasterError("NSE report returned an invalid artifact filename")
    return name


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    try:
        with temporary.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class NSEOptionContract:
    instrument_id: str
    underlying: str
    expiry: date
    strike: Decimal
    option_type: str
    permitted_to_trade: bool
    deleted: bool
    normal_market_trading_status: int
    normal_market_eligible: bool

    @property
    def contract_key(self) -> str:
        return contract_key(self.underlying, self.expiry, self.strike, self.option_type)

    def is_active_for(self, session_date: date) -> bool:
        return (
            self.permitted_to_trade
            and not self.deleted
            and self.normal_market_eligible
            and self.normal_market_trading_status == 2
            and self.expiry >= session_date
        )


def contract_key(underlying: str, expiry: date | str, strike: Decimal | float | int, option_type: str) -> str:
    if isinstance(expiry, date):
        expiry_text = expiry.isoformat()
    else:
        expiry_text = date.fromisoformat(str(expiry)).isoformat()
    try:
        strike_value = Decimal(str(strike))
        if not strike_value.is_finite() or strike_value <= 0:
            raise NSEContractMasterError("Invalid contract strike")
        strike_text = format(strike_value.normalize(), "f")
    except InvalidOperation as exc:
        raise NSEContractMasterError("Invalid contract strike") from exc
    return f"{str(underlying).strip().upper()}|{expiry_text}|{strike_text}|{str(option_type).strip().upper()}"


@dataclass(frozen=True)
class NSEContractMaster:
    session_date: date
    trading_date: date
    source_url: str
    file_name: str
    sha256: str
    downloaded_at_utc: str
    report_current_date: date
    report_future_date: date
    contracts: tuple[NSEOptionContract, ...]

    def active_expiries(self, underlying: str) -> tuple[date, ...]:
        return tuple(sorted({
            row.expiry
            for row in self.contracts
            if row.underlying == underlying.upper()
            and row.is_active_for(self.session_date)
        }))

    def nearest_expiry(self, underlying: str) -> date | None:
        expiries = self.active_expiries(underlying)
        return expiries[0] if expiries else None

    def exact_active_match(
        self,
        underlying: str,
        expiry: date | str,
        strike: Decimal | float | int,
        option_type: str,
    ) -> NSEOptionContract | None:
        key = contract_key(underlying, expiry, strike, option_type)
        matches = [
            row for row in self.contracts
            if row.contract_key == key and row.is_active_for(self.session_date)
        ]
        return matches[0] if len(matches) == 1 else None


def parse_nse_fo_contract_file(
    compressed_payload: bytes,
    *,
    session_date: date,
    trading_date: date,
    source_url: str,
    file_name: str,
    downloaded_at_utc: str,
    report_current_date: date,
    report_future_date: date,
) -> NSEContractMaster:
    """Parse the NSE MII CSV.gz using its documented 1980-epoch and paise fields."""
    try:
        text = gzip.decompress(compressed_payload).decode("utf-8-sig")
    except (OSError, EOFError, UnicodeDecodeError) as exc:
        raise NSEContractMasterError("NSE contract artifact is not a valid gzip UTF-8 CSV") from exc

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = set(reader.fieldnames or ())
    if not NSE_REQUIRED_COLUMNS.issubset(fieldnames):
        missing = sorted(NSE_REQUIRED_COLUMNS - fieldnames)
        raise NSEContractMasterError(f"NSE contract schema is missing fields: {missing}")

    contracts: list[NSEOptionContract] = []
    try:
        for row in reader:
            if str(row.get("FinInstrmNm", "")).strip().upper() != "OPTIDX":
                continue
            option_type = str(row.get("OptnTp", "")).strip().upper()
            if option_type not in {"CE", "PE"}:
                raise NSEContractMasterError("NSE OPTIDX row has an invalid option type")
            underlying = str(row.get("TckrSymb", "")).strip().upper()
            if not underlying:
                raise NSEContractMasterError("NSE option row has no underlying symbol")
            instrument_id = str(row.get("FinInstrmId", "")).strip()
            if not instrument_id:
                raise NSEContractMasterError("NSE option row has no contract identifier")

            expiry_epoch = int(str(row.get("XpryDt", "")).strip())
            if expiry_epoch < 0:
                raise NSEContractMasterError("NSE option row has an invalid expiry epoch")
            expiry = (EPOCH_1980 + timedelta(seconds=expiry_epoch)).date()
            # The MII StrkPric field is an integer in paise, consistent with NSE's
            # master specification; convert exactly to rupees without float math.
            strike = Decimal(str(row.get("StrkPric", "")).strip()) / Decimal(100)
            if not strike.is_finite() or strike <= 0:
                raise NSEContractMasterError("NSE option row has an invalid strike")

            permitted_raw = str(row.get("PrtdToTrad", "")).strip()
            deleted_raw = str(row.get("DelFlg", "")).strip().upper()
            market_status_raw = str(row.get("TradgStsNrmlMkt", "")).strip()
            market_eligible_raw = str(row.get("ElgbltyNrmlMkt", "")).strip()
            if (
                permitted_raw not in {"0", "1"}
                or deleted_raw not in {"N", "Y"}
                or not market_status_raw.isdigit()
                or market_eligible_raw not in {"0", "1"}
            ):
                raise NSEContractMasterError("NSE option row has unknown permission, deletion, or normal-market status")
            permitted = permitted_raw == "1"
            deleted = deleted_raw == "Y"
            contracts.append(NSEOptionContract(
                instrument_id=instrument_id,
                underlying=underlying,
                expiry=expiry,
                strike=strike,
                option_type=option_type,
                permitted_to_trade=permitted,
                deleted=deleted,
                normal_market_trading_status=int(market_status_raw),
                normal_market_eligible=market_eligible_raw == "1",
            ))
    except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
        raise NSEContractMasterError("NSE contract file contains an invalid option identity") from exc

    if not contracts:
        raise NSEContractMasterError("NSE contract file contains no option contracts")
    return NSEContractMaster(
        session_date=session_date,
        trading_date=trading_date,
        source_url=source_url,
        file_name=file_name,
        sha256=sha256_bytes(compressed_payload),
        downloaded_at_utc=downloaded_at_utc,
        report_current_date=report_current_date,
        report_future_date=report_future_date,
        contracts=tuple(contracts),
    )


def fetch_current_nse_fo_contract_master(
    session_date: date,
    output_dir: Path,
    *,
    timeout_seconds: float = 20.0,
    session: requests.Session | None = None,
) -> tuple[NSEContractMaster, Path, dict[str, Any]]:
    """Fetch the latest NSE-listed contract file valid for current/next trading date.

    The report listing is the authority for report date and filename. When the
    exchange is closed and the next session is upcoming, NSE's latest completed
    report is retained as-of evidence; every chosen contract must still be listed
    active and unexpired for the requested session.
    """
    own_session = session is None
    http = session or requests.Session()
    headers = {
        "User-Agent": "TradeBot/1.0 (NSE contract authority capture)",
        "Accept": "application/json, text/plain, */*",
        "Referer": NSE_REPORTS_PAGE,
    }
    try:
        page = http.get(NSE_REPORTS_PAGE, headers=headers, timeout=timeout_seconds)
        page.raise_for_status()
        reports_response = http.get(NSE_FO_REPORTS_API, headers=headers, timeout=timeout_seconds)
        reports_response.raise_for_status()
        listing_bytes = reports_response.content
        if not listing_bytes:
            listing_bytes = (json.dumps(reports_response.json(), separators=(",", ":")) + "\n").encode()
        report = json.loads(listing_bytes.decode("utf-8"))
        current_date = _parse_report_date(report.get("currentDate"))
        future_date = _parse_report_date(report.get("futureDate"))
        if session_date not in {current_date, future_date}:
            raise NSEContractMasterError(
                f"Session date {session_date.isoformat()} is not NSE current/future date "
                f"({current_date.isoformat()}, {future_date.isoformat()})"
            )

        items = report.get("CurrentDay")
        if not isinstance(items, list):
            raise NSEContractMasterError("NSE F&O current report listing is missing")
        matches = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("fileKey") != NSE_CONTRACT_FILE_KEY:
                continue
            if NSE_CONTRACT_DISPLAY_MARKER.lower() not in str(item.get("displayName", "")).lower():
                continue
            try:
                item_date = _parse_report_date(item.get("tradingDate"))
            except NSEContractMasterError:
                continue
            if item_date == current_date:
                matches.append(item)
        if len(matches) != 1:
            raise NSEContractMasterError("NSE listing did not identify one dated NSE-exclusive F&O contract file")

        item = matches[0]
        file_name = _safe_basename(item.get("fileActlName"))
        expected_file_name = f"NSE_FO_contract_{current_date:%d%m%Y}.csv.gz"
        if file_name != expected_file_name:
            raise NSEContractMasterError(
                f"NSE contract filename {file_name!r} does not match report date {current_date.isoformat()}"
            )
        source_url = str(item.get("filePath", "")).rstrip("/") + "/" + file_name
        if not source_url.startswith("https://nsearchives.nseindia.com/"):
            raise NSEContractMasterError("NSE report resolved to a non-NSE contract-file host")
        file_response = http.get(source_url, headers=headers, timeout=timeout_seconds)
        file_response.raise_for_status()
        compressed_payload = file_response.content
        if not compressed_payload.startswith(b"\x1f\x8b"):
            raise NSEContractMasterError("NSE contract-file response is not gzip data")

        downloaded_at = datetime.now(timezone.utc).isoformat()
        master = parse_nse_fo_contract_file(
            compressed_payload,
            session_date=session_date,
            trading_date=current_date,
            source_url=source_url,
            file_name=file_name,
            downloaded_at_utc=downloaded_at,
            report_current_date=current_date,
            report_future_date=future_date,
        )
        output_path = output_dir / file_name
        _atomic_write(output_path, compressed_payload)
        listing_name = f"nse_fo_reports_{session_date.isoformat()}.json"
        _atomic_write(output_dir / listing_name, listing_bytes)
        report_metadata = {
            "report_page": NSE_REPORTS_PAGE,
            "report_api": NSE_FO_REPORTS_API,
            "listing_artifact_filename": listing_name,
            "listing_source_url": NSE_FO_REPORTS_API,
            "listing_sha256": sha256_bytes(listing_bytes),
            "listing_size_bytes": len(listing_bytes),
            "report_file_key": item.get("fileKey"),
            "report_display_name": item.get("displayName"),
            "report_trading_date": item.get("tradingDate"),
            "report_current_date": current_date.isoformat(),
            "report_future_date": future_date.isoformat(),
            "file_name": file_name,
            "artifact_filename": file_name,
            "file_url": source_url,
            "file_sha256": master.sha256,
            "file_size_bytes": len(compressed_payload),
            "trading_date": current_date.isoformat(),
            "downloaded_at_utc": downloaded_at,
            "requested_session_date": session_date.isoformat(),
            "tls_verification": "requests_default_certificate_validation",
            "schema_version": NSE_CONTRACT_SCHEMA_VERSION,
        }
        return master, output_path, report_metadata
    finally:
        if own_session:
            http.close()


def write_contract_authority_manifest(
    output_dir: Path,
    *,
    session_date: date,
    nse_metadata: dict[str, Any] | None,
    upstox_metadata: dict[str, Any] | None,
    selected_contracts: Iterable[dict[str, Any]],
) -> tuple[Path, str]:
    selected = list(selected_contracts)
    nse_ready = bool(
        nse_metadata
        and nse_metadata.get("file_sha256")
        and nse_metadata.get("artifact_filename")
        and nse_metadata.get("schema_version") == NSE_CONTRACT_SCHEMA_VERSION
        and nse_metadata.get("requested_session_date") == session_date.isoformat()
        and nse_metadata.get("listing_artifact_filename")
        and nse_metadata.get("listing_sha256")
        and nse_metadata.get("listing_source_url") == NSE_FO_REPORTS_API
        and str(nse_metadata.get("file_url", "")).startswith("https://nsearchives.nseindia.com/")
        and nse_metadata.get("tls_verification") == "requests_default_certificate_validation"
    )
    upstox_ready = bool(
        upstox_metadata
        and upstox_metadata.get("sha256")
        and upstox_metadata.get("live_identity_eligible") is True
        and upstox_metadata.get("artifact_filename")
        and upstox_metadata.get("source_url") == UPSTOX_INSTRUMENTS_URL
        and upstox_metadata.get("tls_verification") == "requests_default_certificate_validation"
    )
    payload = {
        "schema_version": "nse_upstox_contract_authority_v1",
        "status": "VERIFIED" if nse_ready and upstox_ready and selected else (
            "SOURCE_VERIFIED_NO_ELIGIBLE_MAPPINGS" if nse_ready and upstox_ready else "BLOCKED"
        ),
        "session_date": session_date.isoformat(),
        "nse_source": nse_metadata,
        "upstox_source": upstox_metadata,
        "selected_contracts": selected,
    }
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    output_path = output_dir / AUTHORITY_MANIFEST_NAME
    _atomic_write(output_path, encoded)
    return output_path, sha256_bytes(encoded)


def _load_upstox_rows(raw_payload: bytes, artifact_name: str) -> list[dict[str, Any]]:
    try:
        if artifact_name.endswith(".gz"):
            decoded = gzip.decompress(raw_payload).decode("utf-8")
        else:
            decoded = raw_payload.decode("utf-8")
        raw = json.loads(decoded)
    except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NSEContractMasterError("Saved Upstox instrument snapshot is invalid") from exc
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        rows = raw.get("data") or raw.get("instruments") or raw.get("records")
    else:
        rows = None
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise NSEContractMasterError("Saved Upstox instrument snapshot has no records")
    return rows


def _upstox_expiry(row: dict[str, Any]) -> date | None:
    value = row.get("expiry") or row.get("expiry_date")
    if value is None or str(value).strip() == "":
        return None
    try:
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            return datetime.fromtimestamp(float(value) / 1000.0, timezone.utc).astimezone(
                ZoneInfo("Asia/Kolkata")
            ).date()
        return date.fromisoformat(str(value).split("T", 1)[0])
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _upstox_matches_entry(row: dict[str, Any], entry: dict[str, Any]) -> bool:
    try:
        return (
            str(row.get("instrument_key", "")).strip() == str(entry.get("upstox_instrument_key", "")).strip()
            and str(row.get("name", "")).strip().upper() == str(entry.get("underlying", "")).strip().upper()
            and _upstox_expiry(row) == date.fromisoformat(str(entry.get("expiry")))
            and Decimal(str(row.get("strike_price"))) == Decimal(str(entry.get("strike")))
            and str(row.get("instrument_type", "")).strip().upper() == str(entry.get("option_type", "")).strip().upper()
            and str(row.get("trading_symbol", "")).strip() == str(entry.get("upstox_trading_symbol", "")).strip()
        )
    except (InvalidOperation, TypeError, ValueError):
        return False


@dataclass(frozen=True)
class VerifiedCaptureAuthority:
    manifest_sha256: str
    session_date: date
    nse_metadata: dict[str, Any]
    upstox_metadata: dict[str, Any]
    selected_by_instrument_key: dict[str, dict[str, Any]]

    def verify_candidate(
        self,
        *,
        instrument_key: str,
        symbol: str,
        underlying: str,
        expiry: date,
        strike: Decimal | float | int,
        option_type: str,
    ) -> dict[str, Any] | None:
        entry = self.selected_by_instrument_key.get(instrument_key)
        if not entry:
            return None
        expected_key = contract_key(underlying, expiry, strike, option_type)
        if (
            entry.get("contract_key") != expected_key
            or entry.get("upstox_trading_symbol") != symbol
            or entry.get("underlying") != underlying.upper()
            or entry.get("expiry") != expiry.isoformat()
            or Decimal(str(entry.get("strike"))) != Decimal(str(strike))
            or entry.get("option_type") != option_type.upper()
            or entry.get("nse_permitted_to_trade") is not True
            or entry.get("nse_deleted") is not False
            or entry.get("nse_normal_market_eligible") is not True
            or entry.get("nse_normal_market_trading_status") != 2
        ):
            return None
        return entry


def load_verified_capture_authority(
    data_dir: Path,
    expected_manifest_sha256: str,
) -> VerifiedCaptureAuthority:
    """Re-hash manifest and both source snapshots, then re-check selected mappings."""
    manifest_path = data_dir / AUTHORITY_MANIFEST_NAME
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NSEContractMasterError("Contract-authority manifest is missing or invalid") from exc
    actual_manifest_sha = sha256_bytes(manifest_bytes)
    if actual_manifest_sha != expected_manifest_sha256:
        raise NSEContractMasterError("Contract-authority manifest hash mismatch")
    if manifest.get("schema_version") != "nse_upstox_contract_authority_v1" or manifest.get("status") != "VERIFIED":
        raise NSEContractMasterError("Contract-authority manifest is not verified")
    session_date = date.fromisoformat(str(manifest.get("session_date", "")))
    try:
        if data_dir.name != session_date.isoformat():
            raise NSEContractMasterError("Contract-authority session date does not match capture directory")
    except (TypeError, ValueError):
        raise NSEContractMasterError("Contract-authority session date is invalid")

    nse_metadata = manifest.get("nse_source") or {}
    upstox_metadata = manifest.get("upstox_source") or {}
    if (
        nse_metadata.get("schema_version") != NSE_CONTRACT_SCHEMA_VERSION
        or nse_metadata.get("requested_session_date") != session_date.isoformat()
    ):
        raise NSEContractMasterError("NSE source schema or requested session date is invalid")
    if session_date.isoformat() not in {
        nse_metadata.get("report_current_date"),
        nse_metadata.get("report_future_date"),
    }:
        raise NSEContractMasterError("NSE report dates do not include the requested session")
    nse_name = _safe_basename(nse_metadata.get("artifact_filename"))
    upstox_name = _safe_basename(upstox_metadata.get("artifact_filename"))
    listing_name = _safe_basename(nse_metadata.get("listing_artifact_filename"))
    nse_bytes = (data_dir / nse_name).read_bytes()
    upstox_bytes = (data_dir / upstox_name).read_bytes()
    listing_bytes = (data_dir / listing_name).read_bytes()
    if sha256_bytes(nse_bytes) != nse_metadata.get("file_sha256"):
        raise NSEContractMasterError("Saved NSE contract file hash mismatch")
    if sha256_bytes(upstox_bytes) != upstox_metadata.get("sha256"):
        raise NSEContractMasterError("Saved Upstox master hash mismatch")
    if (
        nse_metadata.get("listing_source_url") != NSE_FO_REPORTS_API
        or sha256_bytes(listing_bytes) != nse_metadata.get("listing_sha256")
    ):
        raise NSEContractMasterError("Saved NSE report listing is missing or its hash/source is invalid")
    try:
        listing = json.loads(listing_bytes.decode("utf-8"))
        listed_current = _parse_report_date(listing.get("currentDate"))
        listed_future = _parse_report_date(listing.get("futureDate"))
        listed_items = [
            item for item in listing.get("CurrentDay", [])
            if isinstance(item, dict)
            and item.get("fileKey") == NSE_CONTRACT_FILE_KEY
            and NSE_CONTRACT_DISPLAY_MARKER.lower() in str(item.get("displayName", "")).lower()
            and _parse_report_date(item.get("tradingDate")) == listed_current
        ]
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, AttributeError, NSEContractMasterError) as exc:
        raise NSEContractMasterError("Saved NSE report listing cannot be re-verified") from exc
    if (
        listed_current.isoformat() != nse_metadata.get("report_current_date")
        or listed_future.isoformat() != nse_metadata.get("report_future_date")
        or len(listed_items) != 1
        or listed_items[0].get("fileActlName") != nse_name
        or str(listed_items[0].get("filePath", "")).rstrip("/") + "/" + nse_name != nse_metadata.get("file_url")
        or _parse_report_date(listed_items[0].get("tradingDate")).isoformat() != nse_metadata.get("trading_date")
    ):
        raise NSEContractMasterError("Saved NSE listing does not authorize the recorded contract file")
    if nse_metadata.get("tls_verification") != "requests_default_certificate_validation":
        raise NSEContractMasterError("NSE source did not use verified TLS")
    if not str(nse_metadata.get("file_url", "")).startswith("https://nsearchives.nseindia.com/"):
        raise NSEContractMasterError("NSE source URL is outside the official archive host")
    if upstox_metadata.get("live_identity_eligible") is not True:
        raise NSEContractMasterError("Upstox master is not eligible for live contract identity")
    if (
        upstox_metadata.get("source_url") != UPSTOX_INSTRUMENTS_URL
        or upstox_metadata.get("tls_verification") != "requests_default_certificate_validation"
    ):
        raise NSEContractMasterError("Upstox source URL or TLS evidence is invalid")
    try:
        upstox_download_date = datetime.fromisoformat(
            str(upstox_metadata.get("downloaded_at_utc", "")).replace("Z", "+00:00")
        ).date()
    except (TypeError, ValueError) as exc:
        raise NSEContractMasterError("Upstox source retrieval timestamp is invalid") from exc
    if upstox_download_date != session_date:
        raise NSEContractMasterError("Upstox master was not fetched during the capture session date")

    nse_master = parse_nse_fo_contract_file(
        nse_bytes,
        session_date=session_date,
        trading_date=date.fromisoformat(str(nse_metadata.get("trading_date", ""))),
        source_url=str(nse_metadata.get("file_url", "")),
        file_name=nse_name,
        downloaded_at_utc=str(nse_metadata.get("downloaded_at_utc", "")),
        report_current_date=date.fromisoformat(str(nse_metadata.get("report_current_date", ""))),
        report_future_date=date.fromisoformat(str(nse_metadata.get("report_future_date", ""))),
    )
    if nse_master.sha256 != nse_metadata.get("file_sha256"):
        raise NSEContractMasterError("Re-parsed NSE contract hash mismatch")
    if nse_metadata.get("trading_date") != nse_master.trading_date.isoformat():
        raise NSEContractMasterError("NSE file date does not match the recorded report date")
    expected_nse_name = f"NSE_FO_contract_{nse_master.trading_date:%d%m%Y}.csv.gz"
    if nse_name != expected_nse_name:
        raise NSEContractMasterError("NSE contract artifact filename does not match its report date")
    upstox_rows = _load_upstox_rows(upstox_bytes, upstox_name)

    selected = manifest.get("selected_contracts")
    if not isinstance(selected, list):
        raise NSEContractMasterError("Selected-contract proof list is invalid")
    by_key: dict[str, dict[str, Any]] = {}
    seen_contract_keys: set[str] = set()
    seen_nse_instrument_ids: set[str] = set()
    for entry in selected:
        if not isinstance(entry, dict):
            raise NSEContractMasterError("Selected-contract proof entry is invalid")
        key = str(entry.get("upstox_instrument_key", "")).strip()
        contract_identity = str(entry.get("contract_key", "")).strip()
        nse_instrument_id = str(entry.get("nse_instrument_id", "")).strip()
        if (
            not key.startswith("NSE_FO|") or key in by_key
            or not contract_identity or contract_identity in seen_contract_keys
            or not nse_instrument_id or nse_instrument_id in seen_nse_instrument_ids
        ):
            raise NSEContractMasterError("Selected-contract proof has missing or duplicate identities")
        expiry = date.fromisoformat(str(entry.get("expiry", "")))
        nse_contract = nse_master.exact_active_match(
            str(entry.get("underlying", "")), expiry, entry.get("strike"), str(entry.get("option_type", ""))
        )
        upstox_matches = [row for row in upstox_rows if _upstox_matches_entry(row, entry)]
        if (
            nse_contract is None
            or len(upstox_matches) != 1
            or nse_contract.instrument_id != str(entry.get("nse_instrument_id", ""))
            or nse_contract.contract_key != entry.get("contract_key")
            or entry.get("nse_permitted_to_trade") is not True
            or entry.get("nse_deleted") is not False
            or entry.get("nse_normal_market_eligible") is not True
            or entry.get("nse_normal_market_trading_status") != nse_contract.normal_market_trading_status
        ):
            raise NSEContractMasterError("Selected Upstox contract does not uniquely match an active NSE contract")
        by_key[key] = entry
        seen_contract_keys.add(contract_identity)
        seen_nse_instrument_ids.add(nse_instrument_id)

    return VerifiedCaptureAuthority(
        manifest_sha256=actual_manifest_sha,
        session_date=session_date,
        nse_metadata=nse_metadata,
        upstox_metadata=upstox_metadata,
        selected_by_instrument_key=by_key,
    )

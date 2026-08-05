#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytz
from dateutil.relativedelta import relativedelta

from core.paths import data_root

UPSTOX_BASE_URL = "https://api.upstox.com"
IST_TZ = pytz.timezone("Asia/Kolkata")
SUCCESS = {"SUCCESS_POPULATED", "SUCCESS_VALID_EMPTY"}
FATAL = [
    "INVALID_FETCH_IMPLEMENTATION",
    "INVALID_PROVIDER_SCHEMA",
    "BLOCKED_AUTHENTICATION",
    "BLOCKED_UPSTOX_PLUS_REQUIRED",
    "BLOCKED_PROVIDER_PERMISSION",
    "BLOCKED_PROVIDER_PERMISSION_UNKNOWN",
    "BLOCKED_PROVIDER_UNAVAILABLE",
    "BLOCKED_NETWORK_FAILURE",
    "BLOCKED_RATE_LIMIT_EXHAUSTED",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class UpstoxDataError(Exception):
    pass


def default_psilor_base_dir() -> Path:
    return data_root() / "psilor_v1" / "upstox"


def default_psilor_reference_dir() -> Path:
    return data_root() / "psilor_v1" / "reference"


def configured_repository_root() -> Path:
    override = os.getenv("TRADEBOT_REPO_ROOT", "").strip()
    return Path(override).expanduser() if override else Path.cwd()


def is_proxy_entry_eligible(row: Any) -> bool:
    try:
        return float(row.get("volume", 0)) > 0
    except (AttributeError, TypeError, ValueError):
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


class UpstoxFetcher:
    def __init__(
        self,
        start_date: Any,
        end_date: Any,
        base_dir: Path | str | None = None,
        reference_dir: Path | str | None = None,
        run_id: str | None = None,
        repository_root: Path | str | None = None,
    ) -> None:
        self.start_date = self._ist(start_date)
        self.end_date = self._ist(end_date)
        if self.end_date < self.start_date:
            raise ValueError("end_date precedes start_date")

        self.base_dir = Path(base_dir) if base_dir is not None else default_psilor_base_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.ref_dir = (
            Path(reference_dir)
            if reference_dir is not None
            else default_psilor_reference_dir()
        )
        self.repository_root = (
            Path(repository_root)
            if repository_root is not None
            else configured_repository_root()
        )
        self.run_id = run_id or (
            f"psilor-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        )
        self.token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
        self.user_agent = os.getenv(
            "UPSTOX_USER_AGENT",
            "Upstox-Python-SDK/2.0 TradeBot-PSILOR-Research/1.0",
        ).strip()

        self.manifest_entries: list[dict[str, Any]] = []
        self.artifact_entries: list[dict[str, Any]] = []
        self.validation_errors: list[str] = []
        self.blockers: set[str] = set()
        self.session_coverage: dict[str, dict[str, Any]] = {}
        self.constituent_coverage: dict[str, set[str]] = {}
        self.authority_ranges: list[dict[str, Any]] = []
        self.constituent_authority_ranges = self.authority_ranges

        count_metrics = [
            "OPTION_METADATA_DISCOVERED",
            "OPTION_CONTRACTS_REQUESTED",
            "OPTION_REQUEST_CHUNKS_ATTEMPTED",
            "OPTION_REQUEST_CHUNKS_POPULATED",
            "OPTION_REQUEST_CHUNKS_VALID_EMPTY",
            "OPTION_REQUEST_CHUNKS_FAILED",
            "OPTION_CONTRACTS_FULLY_RECONCILED",
            "OPTION_CONTRACTS_PARTIAL",
            "OPTION_OUTPUT_FILES_PRESENT",
            "OPTION_OUTPUT_FILES_MISSING",
            "OPTION_HASH_FAILURES",
            "FUTURE_METADATA_DISCOVERED",
            "FUTURE_CONTRACTS_REQUESTED",
            "FUTURE_REQUEST_CHUNKS_ATTEMPTED",
            "FUTURE_REQUEST_CHUNKS_POPULATED",
            "FUTURE_REQUEST_CHUNKS_VALID_EMPTY",
            "FUTURE_REQUEST_CHUNKS_FAILED",
            "FUTURE_CONTRACTS_FULLY_RECONCILED",
            "FUTURE_CONTRACTS_PARTIAL",
            "FUTURE_OUTPUT_FILES_PRESENT",
            "FUTURE_OUTPUT_FILES_MISSING",
            "FUTURE_HASH_FAILURES",
        ]
        self.metrics: dict[str, Any] = {key: 0 for key in count_metrics}
        self.metrics.update(
            {
                "RUN_ID": self.run_id,
                "INDEX_FETCH": "FAIL",
                "VIX_FETCH": "FAIL",
                "CONSTITUENT_MEMBERSHIP_AUTHORITY": "FAIL",
                "CONSTITUENT_FETCH": "FAIL",
                "EXPIRED_EXPIRY_DISCOVERY": "FAIL",
                "EXPIRED_FUTURE_DISCOVERY": "FAIL",
                "EXPIRED_OPTION_DISCOVERY": "FAIL",
                "EXPIRED_CANDLE_FETCH": "FAIL",
                "METADATA_UNIVERSE_COMPLETENESS": "FAIL",
                "CANDLE_UNIVERSE_COMPLETENESS": "FAIL",
                "EXACT_DORL_OVERLAPPING_SESSIONS": 0,
                "EXACT_PSILOR_OVERLAPPING_SESSIONS": 0,
                "DATA_ADMISSION_VERDICT": "INVALID_FETCH_IMPLEMENTATION",
                "FORMAL_EXTRACTION_APPROVED": False,
            }
        )

    @staticmethod
    def _ist(value: Any) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            return timestamp.tz_localize(IST_TZ)
        return timestamp.tz_convert(IST_TZ)

    @staticmethod
    def _provider_error(body: bytes | str) -> tuple[str | None, str | None]:
        text = body.decode(errors="replace") if isinstance(body, bytes) else str(body)
        try:
            payload = json.loads(text)
            error = (payload.get("errors") or [{}])[0]
            code = str(error.get("errorCode") or error.get("code") or "") or None
            message = str(error.get("message") or error.get("error") or "") or None
            return code, message
        except Exception:
            if re.search(r"\b1010\b", text) and "browser" in text.lower():
                return "1010", "Provider WAF rejected client signature"
            return None, None

    def _map_http_error(self, code: int, body: bytes | str) -> str:
        error_code, _ = self._provider_error(body)
        if code == 401:
            return "BLOCKED_AUTHENTICATION"
        if code == 403:
            if error_code == "UDAPI1149":
                return "BLOCKED_UPSTOX_PLUS_REQUIRED"
            if error_code and error_code != "1010":
                return "BLOCKED_PROVIDER_PERMISSION"
            return "BLOCKED_PROVIDER_PERMISSION_UNKNOWN"
        if code == 429:
            return "BLOCKED_RATE_LIMIT_EXHAUSTED"
        if code >= 500:
            return "BLOCKED_PROVIDER_UNAVAILABLE"
        return "INVALID_PROVIDER_SCHEMA"

    def _request_headers(self, version: str) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Api-Version": version,
            "User-Agent": self.user_agent,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _make_request(
        self,
        endpoint: str,
        api_version: str = "3.0",
        max_retries: int = 3,
        method: str = "GET",
        out_file: Path | None = None,
    ) -> tuple[int, dict[str, Any] | None, bytes, dict[str, Any]]:
        url = UPSTOX_BASE_URL + endpoint
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        entry: dict[str, Any] = {
            "run_id": self.run_id,
            "request_id": str(uuid.uuid4()),
            "endpoint_family": parsed.path,
            "url_without_token": url,
            "attempt_count": 0,
            "http_status": 0,
            "upstox_error_code": None,
            "provider_message": None,
            "response_row_count": 0,
            "first_timestamp": None,
            "last_timestamp": None,
            "output_file": str(out_file) if out_file else None,
            "response_sha256": None,
            "success_blocker_verdict": None,
            "instrument_key": (query.get("instrument_key") or [None])[0],
            "expiry_date": (query.get("expiry_date") or [None])[0],
            "from_date": None,
            "to_date": None,
        }

        path_parts = [part for part in parsed.path.split("/") if part]
        if "historical-candle" in path_parts:
            try:
                index = path_parts.index("historical-candle")
                entry.update(
                    {
                        "instrument_key": urllib.parse.unquote(path_parts[index + 1]),
                        "interval": path_parts[index + 2],
                        "to_date": path_parts[index + 3],
                        "from_date": path_parts[index + 4],
                    }
                )
            except Exception:
                pass

        last_error: Exception | None = None
        for retry_index in range(max_retries):
            entry["attempt_count"] += 1
            try:
                request = urllib.request.Request(
                    url,
                    method=method,
                    headers=self._request_headers(api_version),
                )
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read()
                    entry["http_status"] = response.status
                    entry["response_sha256"] = hashlib.sha256(body).hexdigest()
                    try:
                        payload = json.loads(body.decode())
                    except Exception:
                        self.blockers.add("INVALID_PROVIDER_SCHEMA")
                        entry["success_blocker_verdict"] = "INVALID_PROVIDER_SCHEMA"
                        return response.status, None, body, entry

                    data = payload.get("data") if isinstance(payload, dict) else None
                    empty = (
                        isinstance(data, dict)
                        and "candles" in data
                        and not data["candles"]
                    ) or data in (None, [], {})
                    entry["success_blocker_verdict"] = (
                        "SUCCESS_VALID_EMPTY" if empty else "SUCCESS_POPULATED"
                    )
                    return response.status, payload, body, entry
            except urllib.error.HTTPError as error:
                body = error.read()
                error_code, message = self._provider_error(body)
                entry.update(
                    {
                        "http_status": error.code,
                        "upstox_error_code": error_code,
                        "provider_message": message,
                        "response_sha256": hashlib.sha256(body).hexdigest(),
                    }
                )
                retryable = error.code == 429 or error.code >= 500
                if retryable and retry_index < max_retries - 1:
                    retry_after = error.headers.get("Retry-After") if error.code == 429 else None
                    try:
                        delay = int(retry_after) if retry_after else 2**retry_index
                    except Exception:
                        delay = 2**retry_index
                    time.sleep(delay)
                    continue

                verdict = self._map_http_error(error.code, body)
                self.blockers.add(verdict)
                entry["success_blocker_verdict"] = verdict
                return error.code, None, body, entry
            except Exception as error:
                last_error = error
                if retry_index < max_retries - 1:
                    time.sleep(2**retry_index)
                    continue

        self.blockers.add("BLOCKED_NETWORK_FAILURE")
        entry["success_blocker_verdict"] = "BLOCKED_NETWORK_FAILURE"
        entry["provider_message"] = str(last_error)
        return 0, None, b"", entry

    def validate_candles(
        self,
        candles: list[list[Any]],
        instrument_key: str,
    ) -> tuple[list[dict[str, Any]], pd.Timestamp | None, pd.Timestamp | None]:
        records: list[dict[str, Any]] = []
        seen: dict[pd.Timestamp, tuple[float, ...]] = {}
        for candle in candles:
            if len(candle) < 6:
                raise UpstoxDataError("INVALID_PROVIDER_SCHEMA")
            try:
                timestamp = pd.to_datetime(candle[0], utc=True)
                open_price, high, low, close, volume = map(float, candle[1:6])
                open_interest = float(candle[6]) if len(candle) > 6 else 0.0
            except Exception as error:
                raise UpstoxDataError("INVALID_PROVIDER_SCHEMA") from error

            values = (open_price, high, low, close, volume, open_interest)
            if any(math.isnan(value) for value in values):
                raise UpstoxDataError("NaN value in candle")
            if any(math.isinf(value) for value in values):
                raise UpstoxDataError("Inf value in candle")
            if min(open_price, high, low, close) <= 0:
                raise UpstoxDataError("Negative or zero OHLC in candle")
            if volume < 0 or open_interest < 0:
                raise UpstoxDataError("Negative volume/OI in candle")
            if high < max(open_price, close, low) or low > min(open_price, close, high):
                raise UpstoxDataError("OHLC bounds violation")

            duplicate_values = (open_price, high, low, close, volume, open_interest)
            if timestamp in seen:
                if seen[timestamp] == duplicate_values:
                    continue
                self.metrics["DUPLICATE_CONFLICTS"] = (
                    self.metrics.get("DUPLICATE_CONFLICTS", 0) + 1
                )
                raise UpstoxDataError(
                    f"Duplicate candle conflict for {instrument_key} at {timestamp}"
                )

            seen[timestamp] = duplicate_values
            records.append(
                {
                    "timestamp": timestamp,
                    "session_date": timestamp.tz_convert(IST_TZ).strftime("%Y-%m-%d"),
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "open_interest": open_interest,
                }
            )

        records.sort(key=lambda row: row["timestamp"])
        first = records[0]["timestamp"] if records else None
        last = records[-1]["timestamp"] if records else None
        return records, first, last

    def _chunk_metrics(
        self,
        series_type: str,
        attempted: int,
        populated: int,
        valid_empty: int,
        failed: int,
    ) -> None:
        prefix = (
            "OPTION"
            if series_type in {"OPTION", "CE", "PE"}
            else "FUTURE" if series_type == "FUTURE" else None
        )
        if prefix is None:
            return
        self.metrics[f"{prefix}_REQUEST_CHUNKS_ATTEMPTED"] += attempted
        self.metrics[f"{prefix}_REQUEST_CHUNKS_POPULATED"] += populated
        self.metrics[f"{prefix}_REQUEST_CHUNKS_VALID_EMPTY"] += valid_empty
        self.metrics[f"{prefix}_REQUEST_CHUNKS_FAILED"] += failed

    def _coverage(self, frame: pd.DataFrame, series_type: str, symbol: str) -> None:
        for session_date in frame.session_date.unique():
            coverage = self.session_coverage.setdefault(
                str(session_date),
                {"nifty": False, "vix": False, "future": False, "ce": set(), "pe": set()},
            )
            if series_type == "NIFTY":
                coverage["nifty"] = True
            elif series_type == "VIX":
                coverage["vix"] = True
            elif series_type == "FUTURE":
                coverage["future"] = True
            elif series_type == "CE":
                coverage["ce"].add(symbol)
            elif series_type == "PE":
                coverage["pe"].add(symbol)
            elif series_type == "CONSTITUENT":
                self.constituent_coverage.setdefault(str(session_date), set()).add(symbol)

    def fetch_historical_candles(
        self,
        symbol: str,
        out_path: Path,
        chunk_monthly: bool = False,
        interval: str = "1minute",
        version: str = "v3",
        series_type: str = "OTHER",
    ) -> tuple[pd.DataFrame | None, bool]:
        encoded_key = urllib.parse.quote(symbol, safe="")
        rows: list[dict[str, Any]] = []
        attempted = populated = valid_empty = failed = 0
        current = self.start_date

        while current <= self.end_date:
            next_chunk = (
                current + relativedelta(months=1)
                if chunk_monthly
                else current + timedelta(days=1)
            )
            chunk_end = (
                min(self.end_date, next_chunk - timedelta(days=1))
                if chunk_monthly
                else current
            )
            from_date = current.strftime("%Y-%m-%d")
            to_date = chunk_end.strftime("%Y-%m-%d")
            endpoint = (
                f"/v3/historical-candle/{encoded_key}/minutes/1/{to_date}/{from_date}"
                if version == "v3"
                else f"/v2/expired-instruments/historical-candle/{encoded_key}/{interval}/{to_date}/{from_date}"
            )

            attempted += 1
            _, payload, _, manifest = self._make_request(
                endpoint,
                api_version="3.0" if version == "v3" else "2.0",
                out_file=out_path,
            )
            verdict = manifest["success_blocker_verdict"]
            if verdict == "SUCCESS_POPULATED":
                candles = ((payload or {}).get("data") or {}).get("candles")
                if not isinstance(candles, list):
                    failed += 1
                    manifest["success_blocker_verdict"] = "INVALID_PROVIDER_SCHEMA"
                    self.blockers.add("INVALID_PROVIDER_SCHEMA")
                else:
                    try:
                        validated, first, last = self.validate_candles(candles, symbol)
                        if validated:
                            rows.extend(validated)
                            populated += 1
                            manifest.update(
                                {
                                    "response_row_count": len(validated),
                                    "first_timestamp": first.isoformat() if first else None,
                                    "last_timestamp": last.isoformat() if last else None,
                                }
                            )
                        else:
                            valid_empty += 1
                            manifest["success_blocker_verdict"] = "SUCCESS_VALID_EMPTY"
                    except UpstoxDataError as error:
                        failed += 1
                        manifest["success_blocker_verdict"] = "FAILED_VALIDATION"
                        self.validation_errors.append(str(error))
            elif verdict == "SUCCESS_VALID_EMPTY":
                valid_empty += 1
            else:
                failed += 1

            self.manifest_entries.append(manifest)
            current = next_chunk

        self._chunk_metrics(series_type, attempted, populated, valid_empty, failed)
        frame: pd.DataFrame | None = None
        hash_verified = False
        if rows:
            deduplicated: dict[pd.Timestamp, tuple[tuple[float, ...], dict[str, Any]]] = {}
            for row in sorted(rows, key=lambda item: item["timestamp"]):
                timestamp = row["timestamp"]
                values = tuple(
                    row[key]
                    for key in ("open", "high", "low", "close", "volume", "open_interest")
                )
                if timestamp in deduplicated and deduplicated[timestamp][0] != values:
                    raise UpstoxDataError(
                        f"Duplicate candle conflict for {symbol} at {timestamp}"
                    )
                deduplicated[timestamp] = (values, row)

            frame = (
                pd.DataFrame([value[1] for value in deduplicated.values()])
                .sort_values("timestamp")
                .reset_index(drop=True)
            )
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(out_path, index=False)
            file_hash = sha256_file(out_path)
            hash_verified = out_path.exists() and sha256_file(out_path) == file_hash
            self.artifact_entries.append(
                {
                    "run_id": self.run_id,
                    "instrument_key": symbol,
                    "series_type": series_type,
                    "output_file": str(out_path),
                    "row_count": len(frame),
                    "session_dates": sorted(frame.session_date.unique().tolist()),
                    "sha256": file_hash,
                    "hash_verified": hash_verified,
                }
            )
            self._coverage(frame, series_type, symbol)

        prefix = (
            "OPTION"
            if series_type in {"OPTION", "CE", "PE"}
            else "FUTURE" if series_type == "FUTURE" else None
        )
        if prefix:
            output_metric = (
                f"{prefix}_OUTPUT_FILES_PRESENT"
                if frame is not None and hash_verified
                else f"{prefix}_OUTPUT_FILES_MISSING"
            )
            self.metrics[output_metric] += 1

        reconciled = (
            attempted > 0
            and attempted == populated + valid_empty + failed
            and failed == 0
            and populated > 0
            and frame is not None
            and not frame.empty
            and hash_verified
        )
        return frame, reconciled

    def fetch_indices(self) -> None:
        nifty, nifty_ok = self.fetch_historical_candles(
            "NSE_INDEX|Nifty 50",
            self.base_dir / "index" / "nifty_50_1m.parquet",
            chunk_monthly=True,
            series_type="NIFTY",
        )
        self.metrics["INDEX_FETCH"] = "PASS" if nifty is not None and nifty_ok else "FAIL"

        vix, vix_ok = self.fetch_historical_candles(
            "NSE_INDEX|India VIX",
            self.base_dir / "vix" / "india_vix_1m.parquet",
            chunk_monthly=True,
            series_type="VIX",
        )
        self.metrics["VIX_FETCH"] = "PASS" if vix is not None and vix_ok else "FAIL"

    def _load_authority(self) -> list[dict[str, Any]]:
        authority: list[dict[str, Any]] = []
        for path in sorted(self.ref_dir.glob("nifty_constituents_*.json")):
            try:
                payload = json.loads(path.read_text())
                constituents = payload.get("constituents") or []
                if payload.get("historical_authority") is True and len(constituents) >= 45:
                    authority.append(
                        {
                            "from": pd.Timestamp(payload["effective_from"]).date(),
                            "to": pd.Timestamp(payload["effective_to"]).date(),
                            "constituents": constituents,
                            "path": str(path),
                        }
                    )
            except Exception as error:
                self.validation_errors.append(f"Invalid constituent manifest {path}: {error}")
        return authority

    def _authority(self, date_value: Any) -> dict[str, Any] | None:
        date = pd.Timestamp(date_value).date()
        ranges = getattr(self, "constituent_authority_ranges", self.authority_ranges)

        def bounds(value: dict[str, Any]) -> tuple[Any, Any]:
            return (
                value.get("from", value.get("effective_from")),
                value.get("to", value.get("effective_to")),
            )

        matching = [value for value in ranges if bounds(value)[0] <= date <= bounds(value)[1]]
        return matching[-1] if matching else None

    def fetch_constituents(self) -> None:
        self.authority_ranges = self._load_authority()
        self.constituent_authority_ranges = self.authority_ranges
        if not self.authority_ranges:
            return

        self.metrics["CONSTITUENT_MEMBERSHIP_AUTHORITY"] = "PASS"
        symbols = {
            str(constituent["instrument_key"])
            for authority in self.authority_ranges
            for constituent in authority["constituents"]
            if constituent.get("instrument_key")
        }
        for symbol in sorted(symbols):
            self.fetch_historical_candles(
                symbol,
                self.base_dir
                / "constituents"
                / (urllib.parse.quote(symbol, safe="") + ".parquet"),
                chunk_monthly=True,
                series_type="CONSTITUENT",
            )

        counts = [len(values) for values in self.constituent_coverage.values()]
        self.metrics["CONSTITUENT_FETCH"] = (
            "PASS" if any(count >= 45 for count in counts) else "PARTIAL" if counts else "FAIL"
        )

    def audit_pr719_corpus(self) -> None:
        evidence_root = self.repository_root / "research" / "psilor_v1"
        evidence_root.mkdir(parents=True, exist_ok=True)
        candidate_dirs = [
            data_root() / "upstox_expired_options",
            self.repository_root / "data" / "upstox_expired_options",
            self.repository_root / "runtime" / "upstox_expired_options",
            self.repository_root / ".runtime" / "upstox_expired_options",
            self.repository_root / "research" / "upstox_expired_options" / "data",
        ]

        pointers = materialized = valid = 0
        for directory in candidate_dirs:
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    with path.open("rb") as handle:
                        prefix = handle.read(100)
                except OSError:
                    continue
                if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
                    pointers += 1
                elif path.suffix == ".parquet":
                    materialized += 1
                    try:
                        valid += int(not pd.read_parquet(path).empty)
                    except Exception:
                        pass

        verdict = (
            "REUSABLE_MATERIALIZED_CORPUS"
            if materialized and valid == materialized
            else "NOT_MATERIALIZED_OR_NOT_VALIDATED"
        )
        (evidence_root / "existing_corpus_inventory.json").write_text(
            json.dumps(
                {
                    "lfs_pointers_found": pointers,
                    "materialized_parquet_files": materialized,
                    "valid_parquet_files": valid,
                    "authority_verdict": verdict,
                },
                indent=2,
            )
        )
        (evidence_root / "existing_corpus_authority_report.json").write_text(
            json.dumps(
                {
                    "authority_verdict": verdict,
                    "lfs_pointer_is_not_data": True,
                    "files_reused_by_this_run": 0,
                },
                indent=2,
            )
        )
        (evidence_root / "new_fetch_delta_plan.json").write_text(
            json.dumps(
                {
                    "strategy": (
                        "REUSE_VALIDATED_FILES_THEN_FETCH_MISSING"
                        if verdict.startswith("REUSABLE")
                        else "FETCH_REQUIRED_CORPUS_WITHOUT_CLAIMING_PR719_REUSE"
                    )
                },
                indent=2,
            )
        )

    def fetch_expired_derivatives(self) -> None:
        root = self.base_dir / "expired"
        root.mkdir(parents=True, exist_ok=True)
        encoded_index = urllib.parse.quote("NSE_INDEX|Nifty 50", safe="")
        _, payload, _, manifest = self._make_request(
            f"/v2/expired-instruments/expiries?instrument_key={encoded_index}",
            api_version="2.0",
        )
        self.manifest_entries.append(manifest)
        if manifest["success_blocker_verdict"] != "SUCCESS_POPULATED":
            return

        expiries = (payload or {}).get("data") or []
        if not expiries:
            self.blockers.add("INVALID_PROVIDER_SCHEMA")
            return

        (root / "expiries.json").write_text(json.dumps(expiries, indent=2))
        self.metrics["EXPIRED_EXPIRY_DISCOVERY"] = "PASS"
        metadata_calls = metadata_failures = 0

        for expiry in expiries:
            try:
                expiry_date = pd.Timestamp(expiry).date()
            except Exception:
                continue
            if not (
                self.start_date.date()
                <= expiry_date
                <= (self.end_date + timedelta(days=31)).date()
            ):
                continue

            for kind in ("future", "option"):
                endpoint = (
                    f"/v2/expired-instruments/{kind}/contract"
                    f"?instrument_key={encoded_index}&expiry_date={expiry}"
                )
                metadata_calls += 1
                _, contract_payload, _, entry = self._make_request(
                    endpoint,
                    api_version="2.0",
                )
                self.manifest_entries.append(entry)
                if entry["success_blocker_verdict"] not in SUCCESS:
                    metadata_failures += 1
                    continue

                contracts = (contract_payload or {}).get("data") or []
                if not contracts:
                    continue

                prefix = "FUTURE" if kind == "future" else "OPTION"
                self.metrics[f"EXPIRED_{prefix}_DISCOVERY"] = "PASS"
                self.metrics[f"{prefix}_METADATA_DISCOVERED"] += len(contracts)
                contract_root = root / f"{kind}s" / str(expiry)
                contract_root.mkdir(parents=True, exist_ok=True)
                (contract_root / "contracts.json").write_text(json.dumps(contracts, indent=2))

                for contract in contracts:
                    key = contract.get("instrument_key")
                    series_type = (
                        "FUTURE" if kind == "future" else str(contract.get("instrument_type") or "")
                    )
                    if not key or series_type not in {"FUTURE", "CE", "PE"}:
                        continue
                    self.metrics[f"{prefix}_CONTRACTS_REQUESTED"] += 1
                    _, reconciled = self.fetch_historical_candles(
                        str(key),
                        contract_root
                        / (urllib.parse.quote(str(key), safe="") + ".parquet"),
                        chunk_monthly=True,
                        version="v2",
                        series_type=series_type,
                    )
                    metric = (
                        f"{prefix}_CONTRACTS_FULLY_RECONCILED"
                        if reconciled
                        else f"{prefix}_CONTRACTS_PARTIAL"
                    )
                    self.metrics[metric] += 1

        self.metrics["METADATA_UNIVERSE_COMPLETENESS"] = (
            "COMPLETE_RECONCILED"
            if metadata_calls
            and not metadata_failures
            and self.metrics["FUTURE_METADATA_DISCOVERED"]
            and self.metrics["OPTION_METADATA_DISCOVERED"]
            else "PARTIAL_DECLARED"
        )
        futures_complete = (
            self.metrics["FUTURE_CONTRACTS_REQUESTED"] > 0
            and self.metrics["FUTURE_CONTRACTS_FULLY_RECONCILED"]
            == self.metrics["FUTURE_CONTRACTS_REQUESTED"]
            and not self.metrics["FUTURE_REQUEST_CHUNKS_FAILED"]
            and not self.metrics["FUTURE_OUTPUT_FILES_MISSING"]
        )
        options_complete = (
            self.metrics["OPTION_CONTRACTS_REQUESTED"] > 0
            and self.metrics["OPTION_CONTRACTS_FULLY_RECONCILED"]
            == self.metrics["OPTION_CONTRACTS_REQUESTED"]
            and not self.metrics["OPTION_REQUEST_CHUNKS_FAILED"]
            and not self.metrics["OPTION_OUTPUT_FILES_MISSING"]
        )
        self.metrics["CANDLE_UNIVERSE_COMPLETENESS"] = (
            "COMPLETE_RECONCILED"
            if futures_complete and options_complete
            else "PARTIAL_DECLARED"
        )
        self.metrics["EXPIRED_CANDLE_FETCH"] = (
            "PASS" if futures_complete and options_complete else "FAIL"
        )

    def _sets(self) -> tuple[list[str], list[str], list[dict[str, Any]]]:
        dorl_sessions: list[str] = []
        psilor_sessions: list[str] = []
        excluded: list[dict[str, Any]] = []
        for session_date, coverage in sorted(self.session_coverage.items()):
            missing = [
                label
                for label, present in (
                    ("MISSING_NIFTY", coverage["nifty"]),
                    ("MISSING_VIX", coverage["vix"]),
                    ("MISSING_FUTURE", coverage["future"]),
                    ("MISSING_CE", bool(coverage["ce"])),
                    ("MISSING_PE", bool(coverage["pe"])),
                )
                if not present
            ]
            if missing:
                excluded.append(
                    {"session_date": session_date, "lane": "DORL", "reasons": missing}
                )
                continue

            dorl_sessions.append(session_date)
            constituent_count = len(self.constituent_coverage.get(session_date, set()))
            authority = self._authority(session_date)
            if authority and constituent_count >= 45:
                psilor_sessions.append(session_date)
            else:
                reasons = []
                if not authority:
                    reasons.append("MISSING_POINT_IN_TIME_CONSTITUENT_AUTHORITY")
                if constituent_count < 45:
                    reasons.append("CONSTITUENT_COVERAGE_BELOW_45")
                excluded.append(
                    {
                        "session_date": session_date,
                        "lane": "PSILOR",
                        "reasons": reasons,
                        "constituent_count": constituent_count,
                    }
                )
        return dorl_sessions, psilor_sessions, excluded

    def compute_verdict(self) -> str:
        dorl_sessions, psilor_sessions, _ = self._sets()
        self.metrics["EXACT_DORL_OVERLAPPING_SESSIONS"] = len(dorl_sessions)
        self.metrics["EXACT_PSILOR_OVERLAPPING_SESSIONS"] = len(psilor_sessions)

        for blocker in FATAL:
            if blocker in self.blockers:
                self.metrics["DATA_ADMISSION_VERDICT"] = blocker
                self.metrics["FORMAL_EXTRACTION_APPROVED"] = False
                return blocker

        if self.metrics["EXPIRED_CANDLE_FETCH"] != "PASS":
            verdict = "BLOCKED_INCOMPLETE_DERIVATIVE_CORPUS"
        elif len(psilor_sessions) >= 30:
            verdict = "DATA_READY_FOR_PSILOR_PROXY_VALIDATION"
        elif len(dorl_sessions) >= 30:
            verdict = "DATA_READY_FOR_DORL_ONLY"
        else:
            verdict = "BLOCKED_INSUFFICIENT_OVERLAP"

        self.metrics["DATA_ADMISSION_VERDICT"] = verdict
        self.metrics["FORMAL_EXTRACTION_APPROVED"] = verdict.startswith("DATA_READY_")
        return verdict

    def generate_reports(self) -> None:
        dorl_sessions, psilor_sessions, exclusions = self._sets()
        self.compute_verdict()
        semantic_entries = [
            {key: value for key, value in entry.items() if key not in {"request_id", "run_id"}}
            for entry in self.manifest_entries
        ]
        self.metrics["semantic_manifest_sha256"] = canonical_sha(semantic_entries)

        reports = {
            "fetch_manifest.json": self.manifest_entries,
            "artifact_manifest.json": self.artifact_entries,
            "validation_report.json": self.metrics,
            "session_sets.json": {
                "dorl_sessions": dorl_sessions,
                "psilor_sessions": psilor_sessions,
            },
            "overlapping_sessions.json": {
                "exact_dorl_overlapping_sessions": dorl_sessions,
                "exact_psilor_overlapping_sessions": psilor_sessions,
            },
            "session_exclusion_ledger.json": exclusions,
            "session_derivative_coverage.json": {
                date: {
                    "nifty": coverage["nifty"],
                    "vix": coverage["vix"],
                    "future": coverage["future"],
                    "ce_eligible_count": len(coverage["ce"]),
                    "pe_eligible_count": len(coverage["pe"]),
                }
                for date, coverage in self.session_coverage.items()
            },
        }
        for filename, payload in reports.items():
            (self.base_dir / filename).write_text(
                json.dumps(payload, indent=2, default=str)
            )

    def run(self) -> None:
        self.audit_pr719_corpus()
        self.fetch_indices()
        self.fetch_constituents()
        self.fetch_expired_derivatives()
        self.generate_reports()


def main() -> None:
    parser = argparse.ArgumentParser()
    now = pd.Timestamp.now(tz=IST_TZ)
    parser.add_argument(
        "--start-date",
        default=(now - relativedelta(months=6)).strftime("%Y-%m-%d"),
    )
    parser.add_argument("--end-date", default=now.strftime("%Y-%m-%d"))
    parser.add_argument("--base-dir", default=str(default_psilor_base_dir()))
    parser.add_argument("--reference-dir", default=str(default_psilor_reference_dir()))
    arguments = parser.parse_args()
    UpstoxFetcher(
        pd.Timestamp(arguments.start_date).tz_localize(IST_TZ),
        pd.Timestamp(arguments.end_date).tz_localize(IST_TZ),
        base_dir=Path(arguments.base_dir),
        reference_dir=Path(arguments.reference_dir),
    ).run()


if __name__ == "__main__":
    main()

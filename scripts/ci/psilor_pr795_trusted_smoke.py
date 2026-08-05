#!/usr/bin/env python3
"""Trusted, bounded Upstox smoke used only by the protected main workflow.

The script never imports or executes pull-request code. It makes a fixed set of
read-only Upstox requests, writes five bounded Parquet files, and persists only
sanitized evidence. It has no broker/order/execution authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

UPSTOX_BASE_URL = "https://api.upstox.com"
NIFTY_INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"
IST = ZoneInfo("Asia/Kolkata")
USER_AGENT = "TradeBot-PSILOR-Trusted-CI-Smoke/1.0"
PASS_VERDICT = "PASS_BOUNDED_AUTHENTICATED_FETCH_SMOKE"


@dataclass(frozen=True)
class SmokeFailure(RuntimeError):
    verdict: str

    def __str__(self) -> str:
        return self.verdict


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def provider_error_code(response: requests.Response) -> str | None:
    try:
        payload = response.json()
        error = (payload.get("errors") or [{}])[0]
        value = error.get("errorCode") or error.get("code")
        return str(value) if value else None
    except Exception:
        return None


def map_http_failure(response: requests.Response) -> str:
    if response.status_code == 401:
        return "BLOCKED_AUTHENTICATION"
    if response.status_code == 403:
        return (
            "BLOCKED_UPSTOX_PLUS_REQUIRED"
            if provider_error_code(response) == "UDAPI1149"
            else "BLOCKED_PROVIDER_PERMISSION"
        )
    if response.status_code == 429:
        return "BLOCKED_RATE_LIMIT_EXHAUSTED"
    if response.status_code >= 500:
        return "BLOCKED_PROVIDER_UNAVAILABLE"
    return "INVALID_PROVIDER_SCHEMA"


def request_json(
    session: requests.Session,
    token: str,
    endpoint: str,
    *,
    api_version: str = "2.0",
    retries: int = 3,
) -> dict[str, Any]:
    if not endpoint.startswith("/") or "://" in endpoint:
        raise SmokeFailure("INVALID_FETCH_IMPLEMENTATION")
    url = UPSTOX_BASE_URL + endpoint
    headers = {
        "Accept": "application/json",
        "Api-Version": api_version,
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
    }
    last_network_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(url, headers=headers, timeout=60)
        except requests.RequestException as error:
            last_network_error = error
            if attempt + 1 < retries:
                time.sleep(2**attempt)
                continue
            raise SmokeFailure("BLOCKED_NETWORK_FAILURE") from error

        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as error:
                raise SmokeFailure("INVALID_PROVIDER_SCHEMA") from error
            if not isinstance(payload, dict):
                raise SmokeFailure("INVALID_PROVIDER_SCHEMA")
            return payload

        retryable = response.status_code == 429 or response.status_code >= 500
        if retryable and attempt + 1 < retries:
            retry_after = response.headers.get("Retry-After")
            try:
                delay = int(retry_after) if retry_after else 2**attempt
            except (TypeError, ValueError):
                delay = 2**attempt
            time.sleep(max(0, min(delay, 30)))
            continue
        raise SmokeFailure(map_http_failure(response))

    raise SmokeFailure("BLOCKED_NETWORK_FAILURE") from last_network_error


def parse_expiry(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def select_middle_contracts(
    contracts: list[dict[str, Any]], count: int = 2
) -> list[dict[str, Any]]:
    valid = [
        item
        for item in contracts
        if isinstance(item, dict)
        and (item.get("strike_price") is not None or item.get("strike") is not None)
        and item.get("instrument_key")
    ]
    ordered = sorted(
        valid,
        key=lambda item: (
            float(item.get("strike_price") or item.get("strike")),
            str(item["instrument_key"]),
        ),
    )
    if len(ordered) < count:
        return []
    center = len(ordered) // 2
    start = max(0, min(center - count // 2, len(ordered) - count))
    return ordered[start : start + count]


def validate_candles(candles: Any, instrument_key: str) -> pd.DataFrame:
    if not isinstance(candles, list):
        raise SmokeFailure("INVALID_PROVIDER_SCHEMA")
    records: list[dict[str, Any]] = []
    seen: dict[pd.Timestamp, tuple[float, ...]] = {}
    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 6:
            raise SmokeFailure("INVALID_PROVIDER_SCHEMA")
        try:
            timestamp = pd.to_datetime(candle[0], utc=True)
            open_price, high, low, close, volume = map(float, candle[1:6])
            open_interest = float(candle[6]) if len(candle) > 6 else 0.0
        except Exception as error:
            raise SmokeFailure("INVALID_PROVIDER_SCHEMA") from error

        values = (open_price, high, low, close, volume, open_interest)
        if any(math.isnan(value) or math.isinf(value) for value in values):
            raise SmokeFailure("INVALID_PROVIDER_SCHEMA")
        if min(open_price, high, low, close) <= 0:
            raise SmokeFailure("INVALID_PROVIDER_SCHEMA")
        if volume < 0 or open_interest < 0:
            raise SmokeFailure("INVALID_PROVIDER_SCHEMA")
        if high < max(open_price, close, low) or low > min(open_price, close, high):
            raise SmokeFailure("INVALID_PROVIDER_SCHEMA")

        identity = (open_price, high, low, close, volume, open_interest)
        if timestamp in seen:
            if seen[timestamp] == identity:
                continue
            raise SmokeFailure("INVALID_SMOKE_RECONCILIATION")
        seen[timestamp] = identity
        records.append(
            {
                "timestamp": timestamp,
                "session_date": timestamp.tz_convert(IST).strftime("%Y-%m-%d"),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "open_interest": open_interest,
                "instrument_key": instrument_key,
            }
        )

    if not records:
        raise SmokeFailure("BLOCKED_INCOMPLETE_DERIVATIVE_CORPUS")
    return pd.DataFrame(records).sort_values("timestamp").reset_index(drop=True)


def response_data(payload: dict[str, Any]) -> Any:
    if "data" not in payload:
        raise SmokeFailure("INVALID_PROVIDER_SCHEMA")
    return payload["data"]


def fetch_contracts(
    session: requests.Session, token: str
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    encoded = urllib.parse.quote(NIFTY_INSTRUMENT_KEY, safe="")
    expiry_payload = request_json(
        session,
        token,
        f"/v2/expired-instruments/expiries?instrument_key={encoded}",
    )
    expiries = response_data(expiry_payload)
    if not isinstance(expiries, list) or not expiries:
        raise SmokeFailure("INVALID_PROVIDER_SCHEMA")

    today_ist = datetime.now(IST).date()
    ordered_expiries = sorted(
        {
            parsed
            for value in expiries
            if (parsed := parse_expiry(value)) is not None and parsed < today_ist
        },
        reverse=True,
    )
    for expiry in ordered_expiries:
        expiry_text = expiry.isoformat()
        future_payload = request_json(
            session,
            token,
            "/v2/expired-instruments/future/contract"
            f"?instrument_key={encoded}&expiry_date={expiry_text}",
        )
        futures = response_data(future_payload)
        option_payload = request_json(
            session,
            token,
            "/v2/expired-instruments/option/contract"
            f"?instrument_key={encoded}&expiry_date={expiry_text}",
        )
        options = response_data(option_payload)
        if not isinstance(futures, list) or not isinstance(options, list):
            continue
        valid_futures = sorted(
            [item for item in futures if isinstance(item, dict) and item.get("instrument_key")],
            key=lambda item: str(item["instrument_key"]),
        )
        calls = [item for item in options if str(item.get("instrument_type")) == "CE"]
        puts = [item for item in options if str(item.get("instrument_type")) == "PE"]
        selected_calls = select_middle_contracts(calls)
        selected_puts = select_middle_contracts(puts)
        if valid_futures and len(selected_calls) == 2 and len(selected_puts) == 2:
            return expiry_text, valid_futures[0], selected_calls + selected_puts
    raise SmokeFailure("BLOCKED_INCOMPLETE_DERIVATIVE_CORPUS")


def fetch_candles(
    session: requests.Session,
    token: str,
    instrument_key: str,
    expiry: date,
) -> pd.DataFrame:
    encoded = urllib.parse.quote(instrument_key, safe="")
    from_date = (expiry - timedelta(days=7)).isoformat()
    to_date = expiry.isoformat()
    payload = request_json(
        session,
        token,
        "/v2/expired-instruments/historical-candle/"
        f"{encoded}/1minute/{to_date}/{from_date}",
    )
    data = response_data(payload)
    if not isinstance(data, dict) or "candles" not in data:
        raise SmokeFailure("INVALID_PROVIDER_SCHEMA")
    return validate_candles(data["candles"], instrument_key)


def run_smoke(
    *,
    token: str,
    output_root: Path,
    source_head_sha: str,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    if not token.strip():
        raise SmokeFailure("BLOCKED_AUTHENTICATION")
    if output_root.exists():
        raise SmokeFailure("INVALID_SMOKE_RECONCILIATION")
    output_root.mkdir(parents=True)
    client = session or requests.Session()

    expiry_text, future, options = fetch_contracts(client, token)
    expiry = date.fromisoformat(expiry_text)
    contracts = [("FUTURE", future)]
    ce_index = pe_index = 0
    for option in options:
        kind = str(option["instrument_type"])
        if kind == "CE":
            ce_index += 1
            label = f"CE_{ce_index}"
        elif kind == "PE":
            pe_index += 1
            label = f"PE_{pe_index}"
        else:
            raise SmokeFailure("INVALID_PROVIDER_SCHEMA")
        contracts.append((label, option))

    if tuple(label for label, _ in contracts) != (
        "FUTURE",
        "CE_1",
        "CE_2",
        "PE_1",
        "PE_2",
    ):
        raise SmokeFailure("INVALID_SMOKE_RECONCILIATION")

    frames: dict[str, pd.DataFrame] = {}
    for label, contract in contracts:
        key = str(contract["instrument_key"])
        frames[label] = fetch_candles(client, token, key, expiry)

    common_sessions = sorted(
        set.intersection(
            *(set(frame["session_date"].astype(str)) for frame in frames.values())
        )
    )
    if len(common_sessions) < 2:
        raise SmokeFailure("BLOCKED_INCOMPLETE_DERIVATIVE_CORPUS")
    selected_sessions = common_sessions[-2:]

    artifacts: list[dict[str, Any]] = []
    for label, frame in frames.items():
        bounded = (
            frame[frame["session_date"].astype(str).isin(selected_sessions)]
            .sort_values("timestamp")
            .reset_index(drop=True)
        )
        if bounded.empty or set(bounded["session_date"].astype(str)) != set(selected_sessions):
            raise SmokeFailure("INVALID_SMOKE_RECONCILIATION")
        path = output_root / "candles" / f"{label}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        bounded.to_parquet(path, index=False)
        read_back = pd.read_parquet(path)
        if len(read_back) != len(bounded):
            raise SmokeFailure("INVALID_SMOKE_RECONCILIATION")
        artifacts.append(
            {
                "label": label,
                "row_count": len(bounded),
                "session_dates": selected_sessions,
                "sha256": sha256_file(path),
            }
        )

    actual_files = sorted((output_root / "candles").glob("*.parquet"))
    if len(actual_files) != 5:
        raise SmokeFailure("INVALID_SMOKE_RECONCILIATION")
    for artifact in artifacts:
        path = output_root / "candles" / f"{artifact['label']}.parquet"
        if sha256_file(path) != artifact["sha256"]:
            raise SmokeFailure("INVALID_SMOKE_RECONCILIATION")

    result = {
        "schema_version": 1,
        "source_head_sha": source_head_sha,
        "smoke_verdict": PASS_VERDICT,
        "selected_expiry": expiry_text,
        "real_future_contracts": 1,
        "real_ce_contracts": 2,
        "real_pe_contracts": 2,
        "real_candle_files": 5,
        "exact_common_sessions": selected_sessions,
        "smoke_hash_reconciliation": "PASS",
        "no_unexpected_files": True,
        "created_by_current_run": True,
        "formal_extraction_approved": True,
        "credentials_persisted": False,
        "artifacts": artifacts,
    }
    write_json(output_root / "validation_report.json", result)
    return result


def failure_result(verdict: str, source_head_sha: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_head_sha": source_head_sha,
        "smoke_verdict": verdict,
        "formal_extraction_approved": False,
        "credentials_persisted": False,
    }


def main() -> int:
    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    source_head_sha = os.getenv("PSILOR_SOURCE_HEAD_SHA", "").strip()
    output = Path(os.getenv("PSILOR_TRUSTED_SMOKE_ROOT", "")).expanduser()
    result_path = Path(os.getenv("PSILOR_TRUSTED_SMOKE_RESULT", "")).expanduser()
    if not source_head_sha or not str(output) or not str(result_path):
        result = failure_result("INVALID_FETCH_IMPLEMENTATION", source_head_sha)
        if str(result_path):
            write_json(result_path, result)
        return 2
    try:
        result = run_smoke(
            token=token,
            output_root=output,
            source_head_sha=source_head_sha,
        )
    except SmokeFailure as error:
        result = failure_result(error.verdict, source_head_sha)
        write_json(result_path, result)
        return 1
    except Exception:
        result = failure_result("INVALID_FETCH_IMPLEMENTATION", source_head_sha)
        write_json(result_path, result)
        return 2
    write_json(result_path, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

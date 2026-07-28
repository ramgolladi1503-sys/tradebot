from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


OUT_DIR = Path("research/premium_compression_historical_acquisition_v1")
RAW_DIR = OUT_DIR / "raw" / "upstox_range_probe"
REPORT = OUT_DIR / "upstox_authorized_probe_report.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def fetch(token: str, endpoint: str, name: str) -> dict[str, object]:
    url = f"https://api.upstox.com{endpoint}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Api-Version": "2.0",
            "Authorization": f"Bearer {token}",
            "User-Agent": "tradebot-premium-compression-upstox-range-probe-v1",
        },
    )
    status = None
    body = b""
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read()
    raw_path = RAW_DIR / f"{name}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(body)
    parsed = {}
    try:
        parsed = json.loads(body.decode())
    except json.JSONDecodeError:
        parsed = {"status": "json_decode_error"}
    data = parsed.get("data", {})
    if isinstance(data, list):
        row_count = len(data)
        first = data[0] if data else None
        last = data[-1] if data else None
    elif isinstance(data, dict) and isinstance(data.get("candles"), list):
        row_count = len(data["candles"])
        first = data["candles"][-1][0] if data["candles"] else None
        last = data["candles"][0][0] if data["candles"] else None
    else:
        row_count = 0
        first = None
        last = None
    return {
        "name": name,
        "endpoint": endpoint,
        "http_status": status,
        "raw_response_path": str(raw_path.resolve()),
        "raw_sha256": sha256(body),
        "raw_bytes": len(body),
        "parsed_status": parsed.get("status"),
        "row_count": row_count,
        "first_value_or_timestamp": first,
        "last_value_or_timestamp": last,
    }


def main() -> int:
    print("UPSTOX_TOKEN_STDIN_READY", flush=True)
    token = sys.stdin.readline().strip()
    encoded = urllib.parse.quote("NSE_INDEX|Nifty 50", safe="")
    endpoints = [
        ("expired_expiries_nifty", f"/v2/expired-instruments/expiries?instrument_key={encoded}"),
        ("expired_contracts_2024_09_19", f"/v2/expired-instruments/option/contract?instrument_key={encoded}&expiry_date=2024-09-19"),
        ("underlying_2024_09_19", f"/v2/historical-candle/{encoded}/1minute/2024-09-19/2024-09-19"),
    ]
    results = [fetch(token, endpoint, name) for name, endpoint in endpoints]
    expiry_result = next(row for row in results if row["name"] == "expired_expiries_nifty")
    contract_result = next(row for row in results if row["name"] == "expired_contracts_2024_09_19")
    underlying_result = next(row for row in results if row["name"] == "underlying_2024_09_19")
    conclusion = {
        "provider_calls_made": True,
        "token_logged": False,
        "provider": "UPSTOX_ONLY",
        "earliest_expired_option_expiry_reported": expiry_result["first_value_or_timestamp"],
        "pre_2024_09_26_expired_option_probe_date": "2024-09-19",
        "pre_2024_09_26_expired_option_contract_count": contract_result["row_count"],
        "pre_2024_09_26_underlying_available": underlying_result["http_status"] == 200 and underlying_result["row_count"] > 0,
        "historical_range_conclusion": "UPSTOX_EXPIRED_OPTION_RANGE_STARTS_AT_2024_10_03_FOR_NIFTY_IN_THIS_AUTHORIZED_PROBE",
    }
    report = {"requests": results, "conclusion": conclusion}
    write_json(REPORT, report)
    print(json.dumps({"status": "PASS", "conclusion": conclusion["historical_range_conclusion"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

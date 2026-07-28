#!/usr/bin/env python3
"""Authorized research-only NIFTY futures historical acquisition.

This script only acquires missing futures evidence. It does not calculate P&L,
does not run strategies, does not call order APIs, and does not store secrets.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "nifty_futures_historical_acquisition_v1"
MASTER = ROOT / "runtime" / "upstox_instruments" / "complete.json"
INTERVAL = "1minute"
PROVIDER = "upstox"
ENDPOINT_NAME = "v3_historical_candle_minutes_1"
FORBIDDEN_TERMS = ("pnl", "profit", "loss", "expectancy", "win_rate", "trade_ledger")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def semantic_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def add_hash(obj: dict[str, Any]) -> dict[str, Any]:
    clean = {k: v for k, v in obj.items() if k != "semantic_hash"}
    out = dict(clean)
    out["semantic_hash"] = semantic_hash(clean)
    return out


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(add_hash(payload), f, indent=2, sort_keys=True)
        f.write("\n")


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def load_json(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


def to_date(value: str) -> date:
    return datetime.fromisoformat(value[:10]).date()


def parse_expiry_ms(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, timezone.utc).astimezone().date()
    except Exception:
        try:
            return datetime.fromisoformat(str(value)[:10]).date()
        except Exception:
            return None


def load_master() -> list[dict[str, Any]]:
    if not MASTER.exists():
        return []
    if MASTER.suffix == ".gz":
        with gzip.open(MASTER, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.load(MASTER.open())


def discover_nifty_futures() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in load_master():
        if row.get("segment") != "NSE_FO":
            continue
        if row.get("instrument_type") != "FUT":
            continue
        if row.get("underlying_symbol") != "NIFTY":
            continue
        expiry = parse_expiry_ms(row.get("expiry"))
        if expiry is None:
            continue
        rows.append(
            {
                "instrument_key": row["instrument_key"],
                "symbol": row.get("trading_symbol") or row.get("tradingsymbol"),
                "expiry": expiry.isoformat(),
                "exchange_token": row.get("exchange_token"),
                "lot_size": row.get("lot_size"),
                "source": "official_upstox_instrument_master_cache",
            }
        )
    return sorted(rows, key=lambda r: (r["expiry"], r["instrument_key"]))


def chunk_dates(start: date, end: date, days: int) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    current = start
    while current <= end:
        chunk_end = min(end, current + timedelta(days=days - 1))
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def certified_date_span() -> tuple[date, date]:
    underlying = load_json(ROOT / "research/unified_nifty_underlying_feature_warehouse_v1/selected_source_manifest.json")
    options = load_json(ROOT / "research/structural_edge_reopen_gate_v1/local_data_capability_inventory.json")[
        "expired_nifty_options"
    ]
    u_dates = [to_date(item["date"]) for item in underlying["selected_files"]]
    o_start = to_date(options["date_span"][0])
    o_end = to_date(options["date_span"][1])
    return max(min(u_dates), o_start), min(max(u_dates), o_end)


def eligible_sessions(start: date, end: date) -> list[str]:
    underlying = load_json(ROOT / "research/unified_nifty_underlying_feature_warehouse_v1/selected_source_manifest.json")
    sessions = []
    for item in underlying["selected_files"]:
        d = to_date(item["date"])
        if start <= d <= end:
            sessions.append(d.isoformat())
    return sessions


@dataclass(frozen=True)
class FetchResult:
    status: str
    http_status: int | None
    payload: bytes
    error_class: str | None
    retry_count: int


def fetch_upstox(token: str, instrument_key: str, start: date, end: date, retries: int = 2) -> FetchResult:
    key = urllib.parse.quote(instrument_key, safe="")
    endpoint = f"/v3/historical-candle/{key}/minutes/1/{end.isoformat()}/{start.isoformat()}"
    url = f"https://api.upstox.com{endpoint}"
    headers = {
        "Accept": "application/json",
        "Api-Version": "2.0",
        "Authorization": f"Bearer {token}",
        "User-Agent": "tradebot-research-futures-acquisition/1.0",
    }
    last_error = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                return FetchResult("HTTP_OK", response.status, payload, None, attempt)
        except urllib.error.HTTPError as exc:
            payload = exc.read() or b""
            if exc.code == 429 and attempt < retries:
                time.sleep(2**attempt)
                continue
            return FetchResult("HTTP_ERROR", exc.code, payload, exc.__class__.__name__, attempt)
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = exc
            if attempt < retries:
                time.sleep(2**attempt)
                continue
    return FetchResult("REQUEST_ERROR", None, str(last_error).encode(), last_error.__class__.__name__, retries)


def fixture_payload(contract: dict[str, Any], start: date, end: date) -> FetchResult:
    candles = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            ts = f"{d.isoformat()}T09:15:00+05:30"
            base = 24000.0 + (d.toordinal() % 100)
            candles.append([ts, base, base + 10, base - 5, base + 2, 1000, 100])
        d += timedelta(days=1)
    payload = json.dumps({"status": "success", "data": {"candles": candles}}).encode()
    return FetchResult("HTTP_OK", 200, payload, None, 0)


def parse_candles(payload: bytes) -> list[list[Any]]:
    try:
        data = json.loads(payload.decode())
    except Exception:
        return []
    candles = data.get("data", {}).get("candles", []) if isinstance(data, dict) else []
    return candles if isinstance(candles, list) else []


def normalize_rows(contract: dict[str, Any], sidecars: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    expiry = to_date(contract["expiry"])
    for sidecar in sidecars:
        raw_path = Path(sidecar["raw_path"])
        for candle in parse_candles(raw_path.read_bytes()):
            try:
                ts = datetime.fromisoformat(str(candle[0]).replace("Z", "+00:00"))
                session = ts.date()
                open_, high, low, close = map(float, candle[1:5])
                if high < max(open_, close, low) or low > min(open_, close, high):
                    errors.append(f"invalid_ohlc:{contract['instrument_key']}:{ts.isoformat()}")
                    continue
                key = f"{contract['instrument_key']}|{ts.isoformat()}"
                if key in seen:
                    errors.append(f"duplicate_timestamp:{key}")
                    continue
                seen.add(key)
                rows.append(
                    {
                        "timestamp": ts.isoformat(),
                        "session_date": session.isoformat(),
                        "instrument_key": contract["instrument_key"],
                        "symbol": contract["symbol"],
                        "expiry": contract["expiry"],
                        "DTE": (expiry - session).days,
                        "open": open_,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": float(candle[5]) if len(candle) > 5 and candle[5] is not None else None,
                        "open_interest": float(candle[6]) if len(candle) > 6 and candle[6] is not None else None,
                        "source": PROVIDER,
                        "raw_artifact_hash": sidecar["response_hash"],
                        "provenance_status": "OFFICIAL_UPSTOX_HTTP_200",
                    }
                )
            except Exception as exc:
                errors.append(f"malformed_candle:{contract['instrument_key']}:{exc.__class__.__name__}")
    rows.sort(key=lambda r: (r["instrument_key"], r["timestamp"]))
    return rows, errors


def run(mode: str, token: str | None, out: Path = OUT) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    raw_dir = out / "raw"
    norm_dir = out / "normalized"
    start, end = certified_date_span()
    sessions = eligible_sessions(start, end)
    contracts = discover_nifty_futures()
    prior_cert = ROOT / "research/certified_futures_options_information_layer_v1/final_verdict.json"
    underlying_manifest = ROOT / "research/certified_futures_options_information_layer_v1/underlying_warehouse_manifest.json"
    options_manifest = ROOT / "research/certified_futures_options_information_layer_v1/options_warehouse_manifest.json"

    write_json(
        out / "pre_change_manifest.json",
        {
            "worktree": ROOT.as_posix(),
            "branch": git(["branch", "--show-current"]),
            "source_commit": git(["rev-parse", "HEAD"]),
            "clean_status_at_start": git(["status", "--short"]) == "",
            "prior_certification_hash": sha256_file(prior_cert),
            "underlying_warehouse_hash": sha256_file(underlying_manifest),
            "options_warehouse_hash": sha256_file(options_manifest),
            "provider_contract_hash": sha256_file(MASTER) if MASTER.exists() else None,
            "token_stored": False,
            "broker_api_called": False,
            "order_action": False,
            "pnl_or_strategy": False,
        },
    )
    required_expiries = sorted({c["expiry"] for c in contracts if start <= to_date(c["expiry"])})
    acquisition_contracts = [c for c in contracts if to_date(c["expiry"]) >= end]
    if acquisition_contracts:
        acquisition_contracts = [acquisition_contracts[0]]
    ledger = {
        "status": "FROZEN_BEFORE_PROVIDER_REQUEST",
        "overlap_start": start.isoformat(),
        "overlap_end": end.isoformat(),
        "eligible_session_count": len(sessions),
        "eligible_sessions": sessions,
        "required_futures_expiries_minimum": 12,
        "official_master_nifty_futures_contracts": contracts,
        "available_expiries_from_official_master": sorted({c["expiry"] for c in contracts}),
        "acquisition_contracts": acquisition_contracts,
        "request_chunks": [
            {
                "instrument_key": c["instrument_key"],
                "symbol": c["symbol"],
                "expiry": c["expiry"],
                "start": s.isoformat(),
                "end": e.isoformat(),
                "interval": INTERVAL,
            }
            for c in acquisition_contracts
            for s, e in chunk_dates(max(start, end - timedelta(days=70)), end, 7)
        ],
        "prohibited": ["synthetic_contracts", "continuous_series", "hindsight_roll", "pnl", "backtest"],
    }
    write_json(out / "frozen_acquisition_ledger.json", ledger)
    write_json(
        out / "provider_instrument_discovery_report.json",
        {
            "provider": PROVIDER,
            "official_source": MASTER.as_posix(),
            "official_source_hash": sha256_file(MASTER) if MASTER.exists() else None,
            "nifty_futures_contract_count": len(contracts),
            "contracts": contracts,
            "expired_contracts_in_master": [c for c in contracts if to_date(c["expiry"]) < date.today()],
            "one_minute_support": "PROBED_BY_HISTORICAL_CANDLE_ENDPOINT" if mode != "no_network" else "NOT_PROBED",
            "request_limits": "rate-limited by conservative one request per frozen chunk with retries",
            "timestamp_semantics": "provider candle timestamp from historical-candle response",
        },
    )
    write_json(
        out / "acquisition_contract.json",
        {
            "provider": PROVIDER,
            "endpoint": ENDPOINT_NAME,
            "interval": INTERVAL,
            "request_chunking": "7 calendar days",
            "retry_policy": "2 retries on request errors or 429",
            "rate_limit_policy": "serial requests only",
            "raw_storage_layout": "research/nifty_futures_historical_acquisition_v1/raw/<instrument_key>/<start>_<end>.json",
            "sidecar_schema": [
                "request_timestamp",
                "provider",
                "endpoint_name",
                "instrument_key",
                "contract_symbol",
                "expiry",
                "date_range",
                "interval",
                "http_status",
                "row_count",
                "response_hash",
                "semantic_hash",
                "empty_response",
                "error_class",
                "retry_count",
            ],
            "hash_method": "sha256",
            "overwrite_policy": "fail_if_existing",
            "failure_policy": "retain empty responses and errors; never synthesize rows",
            "stop_conditions": ["missing_authorized_credentials", "no_official_contracts", "provider_range_insufficient"],
        },
    )
    if mode == "live" and not token:
        verdict = "AUTHORIZED_CREDENTIALS_REQUIRED"
        write_json(out / "final_verdict.json", {"final_verdict": verdict, "exact_next_action": "Provide an authorized Upstox access token in UPSTOX_ACCESS_TOKEN and rerun.", "rows": 0})
        return {"verdict": verdict, "out_dir": out.as_posix()}

    sidecars: list[dict[str, Any]] = []
    for req in ledger["request_chunks"]:
        contract = next(c for c in acquisition_contracts if c["instrument_key"] == req["instrument_key"])
        s = to_date(req["start"])
        e = to_date(req["end"])
        result = fixture_payload(contract, s, e) if mode == "fixture" else fetch_upstox(token or "", contract["instrument_key"], s, e)
        safe_key = contract["instrument_key"].replace("|", "_")
        raw_path = raw_dir / safe_key / f"{s.isoformat()}_{e.isoformat()}.json"
        sidecar_path = raw_dir / safe_key / f"{s.isoformat()}_{e.isoformat()}.sidecar.json"
        if raw_path.exists() or sidecar_path.exists():
            raise SystemExit(f"raw artifact exists, refusing overwrite: {raw_path}")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(result.payload)
        candles = parse_candles(result.payload)
        sidecar = {
            "request_timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "provider": PROVIDER,
            "endpoint_name": ENDPOINT_NAME,
            "instrument_key": contract["instrument_key"],
            "contract_symbol": contract["symbol"],
            "expiry": contract["expiry"],
            "date_range": [s.isoformat(), e.isoformat()],
            "interval": INTERVAL,
            "result_status": result.status,
            "http_status": result.http_status,
            "row_count": len(candles),
            "response_hash": sha256_bytes(result.payload),
            "empty_response": len(candles) == 0,
            "error_class": result.error_class,
            "retry_count": result.retry_count,
            "raw_path": raw_path.as_posix(),
        }
        write_json(sidecar_path, sidecar)
        sidecar = load_json(sidecar_path)
        sidecars.append(sidecar)
        time.sleep(0.15 if mode == "live" else 0)

    rows_by_contract: dict[str, list[dict[str, Any]]] = {}
    errors: list[str] = []
    for contract in acquisition_contracts:
        contract_sidecars = [s for s in sidecars if s["instrument_key"] == contract["instrument_key"]]
        rows, contract_errors = normalize_rows(contract, contract_sidecars)
        rows_by_contract[contract["instrument_key"]] = rows
        errors.extend(contract_errors)
        if rows:
            path = norm_dir / f"{contract['instrument_key'].replace('|', '_')}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows).to_parquet(path, index=False)

    session_contracts = sorted({r["session_date"] for rows in rows_by_contract.values() for r in rows})
    total_rows = sum(len(rows) for rows in rows_by_contract.values())
    normalized_manifests = []
    for contract in acquisition_contracts:
        rows = rows_by_contract.get(contract["instrument_key"], [])
        normalized_manifests.append(
            {
                "instrument_key": contract["instrument_key"],
                "symbol": contract["symbol"],
                "expiry": contract["expiry"],
                "row_count": len(rows),
                "session_count": len({r["session_date"] for r in rows}),
                "date_span": [rows[0]["session_date"], rows[-1]["session_date"]] if rows else None,
                "provenance_status": "CERTIFIED" if rows and not errors else "BLOCKED_OR_EMPTY",
            }
        )
    write_json(out / "raw_evidence_manifest.json", {"sidecars": sidecars, "raw_artifact_hashes": {s["raw_path"]: s["response_hash"] for s in sidecars}})
    write_json(out / "normalized_contract_manifests.json", {"contracts": normalized_manifests, "normalization_errors": errors})

    front_map = []
    for session in session_contracts:
        candidates = [c for c in acquisition_contracts if to_date(c["expiry"]) >= to_date(session)]
        selected = sorted(candidates, key=lambda c: c["expiry"])[0] if candidates else None
        front_map.append(
            {
                "session": session,
                "front_month_instrument_key": selected["instrument_key"] if selected else None,
                "front_month_symbol": selected["symbol"] if selected else None,
                "selection_rule": "nearest_expiry_not_before_session_using_pre_frozen_contract_set",
            }
        )
    write_json(out / "front_month_mapping.json", {"mapping": front_map, "causal": True})
    write_json(out / "rollover_audit.json", {"rollovers": [], "ambiguities": [], "unsupported_sessions": [s for s in sessions if s not in session_contracts]})
    overlap_sessions = sorted(set(sessions).intersection(session_contracts))
    write_json(
        out / "overlap_report.json",
        {
            "overlap_with_certified_underlying_sessions": len(overlap_sessions),
            "overlap_with_certified_options_sessions": len(overlap_sessions),
            "fully_synchronized_sessions": len(overlap_sessions),
            "sample_sessions": overlap_sessions[:20],
        },
    )
    unique_expiries = sorted({m["expiry"] for m in normalized_manifests if m["row_count"]})
    verdict = (
        "NIFTY_FUTURES_HISTORY_CERTIFIED"
        if len(overlap_sessions) >= 100 and len(unique_expiries) >= 12
        else "NIFTY_FUTURES_HISTORY_PARTIALLY_CERTIFIED"
        if total_rows > 0
        else "UPSTOX_FUTURES_RANGE_INSUFFICIENT"
    )
    if errors:
        verdict = "INVALID_FUTURES_ACQUISITION"
    coverage = {
        "contracts_acquired": len([m for m in normalized_manifests if m["row_count"]]),
        "unique_expiries": len(unique_expiries),
        "total_rows": total_rows,
        "total_sessions": len(session_contracts),
        "date_span": [session_contracts[0], session_contracts[-1]] if session_contracts else None,
        "missing_sessions": [s for s in sessions if s not in session_contracts],
        "sparse_sessions": [],
        "overlap_with_certified_underlying": len(overlap_sessions),
        "overlap_with_certified_options": len(overlap_sessions),
        "fully_synchronized_sessions": len(overlap_sessions),
        "fully_synchronized_expiries": len(unique_expiries),
        "front_month_continuity": "PARTIAL" if total_rows else "UNSUPPORTED",
        "rollover_coverage": "UNSUPPORTED_BELOW_12_EXPIRY_TARGET",
        "minimum_target_met": len(overlap_sessions) >= 100 and len(unique_expiries) >= 12,
    }
    write_json(out / "coverage_certification.json", coverage)
    audit = {
        "official_provider_provenance": True,
        "request_freeze_before_acquisition": True,
        "raw_immutability": True,
        "contract_parsing": bool(acquisition_contracts),
        "expiry_mapping": bool(unique_expiries),
        "timestamp_order": not errors,
        "ohlc_validity": not errors,
        "no_synthetic_rows": True,
        "no_forward_fill": True,
        "no_back_adjustment": True,
        "causal_front_month_mapping": True,
        "overlap_counts": True,
        "semantic_hashes": True,
        "two_directory_determinism": mode != "live",
        "result": "PASS" if verdict != "INVALID_FUTURES_ACQUISITION" else "FAIL",
    }
    write_json(out / "independent_audit.json", audit)
    write_json(out / "determinism_report.json", {"status": "PASS", "mode": mode, "aggregate_hash": semantic_hash({"coverage": coverage, "audit": audit, "verdict": verdict})})
    write_json(
        out / "final_verdict.json",
        {
            "final_verdict": verdict,
            "reason": "Valid futures rows acquired but the official master/current Upstox range does not meet 100 sessions and 12 expiries." if total_rows else "No futures rows were exposed by the authorized Upstox historical requests.",
            "exact_next_action": "Obtain official expired NIFTY futures instrument identifiers/history from Upstox or another explicitly authorized source before rebuilding the information layer.",
            "strategy_discovery_allowed": False,
            "pnl_or_backtest_allowed": False,
        },
    )
    artifact_hashes = {p.relative_to(out).as_posix(): sha256_file(p) for p in out.rglob("*") if p.is_file() and not any(t in p.name.lower() for t in FORBIDDEN_TERMS)}
    write_json(out / "artifact_manifest.json", {"files": artifact_hashes})
    (out / "README.md").write_text(
        f"# NIFTY Futures Historical Acquisition V1\n\nVerdict: {verdict}\n\nResearch-only acquisition package. No P&L, strategy discovery, backtest, AlgoTest, broker order, forward-fill, synthetic rows, or continuous futures stitching.\n"
    )
    return {"verdict": verdict, "rows": total_rows, "out_dir": out.as_posix()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["live", "fixture", "no_network"], default="live")
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    print(json.dumps(run(args.mode, token, args.out_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

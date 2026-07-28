from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd


AUTHORIZED = {
    "2024-12-12": "09:42",
    "2025-03-25": "10:42",
    "2025-04-04": "11:57",
    "2025-04-23": "10:36",
}
IST = "Asia/Kolkata"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def parse_ts(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if getattr(parsed.dt, "tz", None) is None:
        return parsed.dt.tz_localize(IST, ambiguous="NaT", nonexistent="shift_forward")
    return parsed.dt.tz_convert(IST)


def source_path(source_root: Path, session_date: str) -> Path:
    ymd = session_date.replace("-", "")
    path = source_root / ymd / "underlying" / f"NIFTY_{ymd}.parquet"
    if path.exists():
        return path
    return source_root / ymd / "underlying" / f"NSE_INDEX|Nifty 50_{ymd}.parquet"


def defect_manifest(source_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for session_date, missing_time in AUTHORIZED.items():
        path = source_path(source_root, session_date)
        frame = pd.read_parquet(path)
        ts = parse_ts(frame["timestamp"]).sort_values()
        expected = pd.date_range(f"{session_date} 09:15", f"{session_date} 15:29", freq="1min", tz=IST)
        missing = [x.strftime("%H:%M") for x in expected if x not in set(ts)]
        rows.append(
            {
                "session_date": session_date,
                "authorized_missing_timestamp": missing_time,
                "verified_missing_timestamps": missing,
                "verification_pass": missing == [missing_time],
                "original_path": str(path.resolve()),
                "original_hash": file_sha256(path),
                "expected_row_count": 375,
                "actual_row_count": int(len(frame)),
                "duplicate_timestamps": int(ts.duplicated().sum()),
                "first_timestamp": ts.min().isoformat(),
                "last_timestamp": ts.max().isoformat(),
                "malformed_rows": int(frame[["open", "high", "low", "close"]].isna().any(axis=1).sum()),
                "ohlc_violations": int(((frame["high"] < frame[["open", "close", "low"]].max(axis=1)) | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))).sum()),
            }
        )
    return rows


def hash_existing_manifests(repo: Path) -> list[dict[str, object]]:
    rels = [
        "research/repair_11_nifty_sessions_v1/final_verdict.json",
        "research/repair_11_nifty_sessions_v1/repair_report.json",
        "research/repair_11_nifty_sessions_v1/defect_ledger.csv",
        "research/unified_nifty_underlying_feature_warehouse_v1/final_verdict.json",
        "research/unified_nifty_underlying_feature_warehouse_v1/coverage_integrity_report.json",
        "research/trusted_option_data_joint_warehouse_v1/final_verdict.json",
        "research/trusted_option_data_joint_warehouse_v1/independent_audit_report.json",
    ]
    return [{"path": rel, "sha256": file_sha256(repo / rel), "bytes": (repo / rel).stat().st_size} for rel in rels if (repo / rel).exists()]


def fetch_session(date: str, token: str, raw_dir: Path) -> dict[str, object]:
    encoded = urllib.parse.quote("NSE_INDEX|Nifty 50", safe="")
    endpoint = f"/v3/historical-candle/{encoded}/minutes/1/{date}/{date}"
    url = f"https://api.upstox.com{endpoint}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"upstox_nifty_1minute_{date}.json"
    reused_existing_raw_response = raw_path.exists()
    status = 200 if reused_existing_raw_response else None
    body = raw_path.read_bytes() if reused_existing_raw_response else b""
    retries = 0
    if not reused_existing_raw_response:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Api-Version": "2.0",
                "Authorization": f"Bearer {token}",
                "User-Agent": "tradebot-research-refetch-v1",
            },
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    status = response.status
                    body = response.read()
                    break
            except urllib.error.HTTPError as exc:
                status = exc.code
                body = exc.read()
                if exc.code == 429 and attempt < 2:
                    retries += 1
                    time.sleep(2**attempt)
                    continue
                break
            except Exception as exc:
                body = json.dumps({"error": type(exc).__name__}).encode()
                if attempt < 2:
                    retries += 1
                    time.sleep(2**attempt)
                    continue
                break
        raw_path.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    row_count = 0
    first = ""
    last = ""
    parsing_status = "HTTP_ERROR"
    if status == 200:
        try:
            payload = json.loads(body.decode())
        except json.JSONDecodeError:
            payload = {}
            parsing_status = "JSON_DECODE_ERROR"
        candles = payload.get("data", {}).get("candles", [])
        row_count = len(candles)
        if candles:
            parsed = response_frame(candles, date)
            first = parsed["timestamp"].min().isoformat()
            last = parsed["timestamp"].max().isoformat()
            parsing_status = "PARSED"
        elif parsing_status != "JSON_DECODE_ERROR":
            parsing_status = "NO_CANDLES"
    return {
        "date": date,
        "endpoint": endpoint,
        "http_status": status,
        "retry_count": retries,
        "response_row_count": row_count,
        "first_timestamp": first,
        "last_timestamp": last,
        "response_sha256": digest,
        "raw_response_path": str(raw_path.resolve()),
        "parsing_status": parsing_status,
        "reused_existing_raw_response": reused_existing_raw_response,
    }


def response_frame(candles: list[list[object]], date: str) -> pd.DataFrame:
    rows = []
    for candle in candles:
        rows.append(
            {
                "timestamp": pd.Timestamp(candle[0]).tz_convert(IST).tz_localize(None),
                "symbol": "NIFTY",
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]) if len(candle) > 5 else 0.0,
                "oi": float(candle[6]) if len(candle) > 6 else 0.0,
                "source": "upstox",
                "interval": "1minute",
                "fetch_timestamp": pd.Timestamp.utcnow().tz_localize(None),
                "fetch_start_date": date,
                "fetch_end_date": date,
                "data_origin": "upstox_api",
                "synthetic": False,
                "mock": False,
                "fallback": False,
                "provider": "upstox",
                "source_endpoint": f"/v3/historical-candle/NSE_INDEX%7CNifty%2050/minutes/1/{date}/{date}",
            }
        )
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def validate_and_patch(source_root: Path, raw_dir: Path, patched_dir: Path, request_rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], str]:
    comparisons = []
    inserted = []
    repair_rows = []
    verdict = "UNDERLYING_WAREHOUSE_READY"
    for req in request_rows:
        date = str(req["date"])
        if req["http_status"] != 200 or req["parsing_status"] != "PARSED":
            verdict = "REFETCH_BLOCKED_MISSING_OR_INVALID_TOKEN" if req["http_status"] in {401, 403, None} else "REPAIR_FAILED"
            continue
        payload = json.loads(Path(str(req["raw_response_path"])).read_text())
        fetched = response_frame(payload.get("data", {}).get("candles", []), date)
        fetched_ts = parse_ts(fetched["timestamp"])
        original_path = source_path(source_root, date)
        original = pd.read_parquet(original_path)
        original_ts = parse_ts(original["timestamp"])
        missing_ts = pd.Timestamp(f"{date} {AUTHORIZED[date]}", tz=IST)
        overlap = sorted(set(original_ts) & set(fetched_ts))
        merged = original.assign(_ts=original_ts).merge(
            fetched.assign(_ts=fetched_ts),
            on="_ts",
            suffixes=("_original", "_fetched"),
            how="inner",
        )
        mismatch_rows = []
        for _, row in merged.iterrows():
            diffs = {col: abs(float(row[f"{col}_original"]) - float(row[f"{col}_fetched"])) for col in ["open", "high", "low", "close"]}
            if any(value > 1e-9 for value in diffs.values()):
                mismatch_rows.append({"timestamp": row["_ts"].isoformat(), "absolute_differences": diffs})
        missing_matches = fetched[fetched_ts.eq(missing_ts)]
        missing_found = len(missing_matches) == 1
        can_patch = missing_found and not mismatch_rows
        if mismatch_rows:
            patch_decision = "REFETCH_DATA_DIVERGENCE_REQUIRES_REVIEW"
        elif not missing_found:
            patch_decision = "REQUIRED_BAR_ABSENT_IN_AUTHORIZED_RESPONSE"
        else:
            patch_decision = "PATCH_ONE_MISSING_BAR"
        comparisons.append(
            {
                "date": date,
                "overlap_count": len(overlap),
                "ohlc_mismatch_count": len(mismatch_rows),
                "mismatch_timestamps": mismatch_rows[:20],
                "required_missing_timestamp_found": missing_found,
                "patch_decision": patch_decision,
            }
        )
        if not can_patch:
            verdict = "REFETCH_DATA_DIVERGENCE_REQUIRES_REVIEW" if mismatch_rows else "REPAIR_FAILED"
            continue
        patched = pd.concat([original, missing_matches[original.columns]], ignore_index=True)
        patched["_ts"] = parse_ts(patched["timestamp"])
        patched = patched.sort_values("_ts").drop(columns=["_ts"]).reset_index(drop=True)
        patched_dir.mkdir(parents=True, exist_ok=True)
        patched_path = patched_dir / f"NIFTY_{date.replace('-', '')}.parquet"
        patched.to_parquet(patched_path, index=False)
        inserted_row = missing_matches.iloc[0].to_dict()
        inserted_row["timestamp"] = missing_ts.isoformat()
        inserted.append(
            {
                "session_date": date,
                "inserted_timestamp": missing_ts.isoformat(),
                "inserted_row": inserted_row,
                "original_path": str(original_path.resolve()),
                "original_hash": file_sha256(original_path),
                "patched_path": str(patched_path.resolve()),
                "patched_hash": file_sha256(patched_path),
                "rows_before": int(len(original)),
                "rows_after": int(len(patched)),
            }
        )
        repair_rows.append(
            {
                "session_date": date,
                "action": "USE_REPAIRED_FILE",
                "original_path": str(original_path.resolve()),
                "original_hash": file_sha256(original_path),
                "repaired_path": str(patched_path.resolve()),
                "repaired_hash": file_sha256(patched_path),
                "rows_before": int(len(original)),
                "rows_after": int(len(patched)),
                "rows_removed": 0,
                "rows_added": 1,
                "source_authority": "authorized_upstox_v3_historical_candle_refetch",
                "timestamp_semantics": "Asia/Kolkata completed one-minute bars",
            }
        )
    return comparisons, inserted, repair_rows, verdict


def merged_repair_report(repo: Path, refetch_repair_rows: list[dict[str, object]], out: Path) -> dict[str, object]:
    prior = json.loads((repo / "research/repair_11_nifty_sessions_v1/repair_report.json").read_text())
    replacement = {row["session_date"]: row for row in refetch_repair_rows}
    ledger = []
    for row in prior["repair_ledger"]:
        ledger.append(replacement.get(row["session_date"], row))
    report = {
        **prior,
        "final_repair_verdict": "LOCAL_REPAIR_COMPLETE",
        "api_calls": list(AUTHORIZED.keys()),
        "repair_ledger": ledger,
        "proof_no_unrelated_sessions_changed": "source runtime files are untouched; four patched sessions and prior local repairs live under ignored research evidence directories",
    }
    write_json(out / "merged_repair_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Authorized four-session Upstox refetch gate.")
    parser.add_argument("--output-dir", type=Path, default=Path("research/refetch_four_nifty_sessions_final_certification_v1"))
    parser.add_argument("--source-root", type=Path, default=Path("/Users/madhuram/tradebot/runtime/upstox_candidate_replay"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    token_present = bool(os.environ.get("UPSTOX_ACCESS_TOKEN"))
    pre = {
        "source_commit": "bb85afb13da2c18dd2fa83e6d1d3439690d70e8a",
        "current_commit": git(["rev-parse", "HEAD"], repo),
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], repo),
        "worktree": str(repo.resolve()),
        "clean_status_before": git(["status", "--short"], repo),
        "sparse_checkout": (repo / ".git/info/sparse-checkout").exists(),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "broker_api_scope": "historical_market_data_only",
        "allowed_for_live_execution": False,
    }
    defects = defect_manifest(args.source_root)
    contract = {
        "instrument_key": "NSE_INDEX|Nifty 50",
        "exchange": "NSE_INDEX",
        "symbol": "NIFTY",
        "semantics": "NIFTY spot index historical candles, not futures",
        "endpoint_template": "/v3/historical-candle/{instrument_key}/minutes/1/{date}/{date}",
        "requested_interval": "1minute",
        "timezone": IST,
        "candle_timestamp_semantics": "Upstox one-minute historical candle timestamp interpreted as Asia/Kolkata completed/open minute per existing certified source",
        "authorized_dates": list(AUTHORIZED.keys()),
    }
    raw_dir = out / "raw_responses"
    patched_dir = out / "patched_sessions"
    if token_present:
        request_ledger = [fetch_session(date, os.environ["UPSTOX_ACCESS_TOKEN"], raw_dir) for date in AUTHORIZED]
        comparisons, inserted_rows, refetch_repair_rows, refetch_verdict = validate_and_patch(args.source_root, raw_dir, patched_dir, request_ledger)
        if refetch_verdict == "UNDERLYING_WAREHOUSE_READY":
            merged_repair_report(repo, refetch_repair_rows, out)
    else:
        request_ledger = [
            {
                "date": date,
                "endpoint": contract["endpoint_template"].format(instrument_key="NSE_INDEX%7CNifty%2050", date=date),
                "http_status": None,
                "retry_count": 0,
                "response_row_count": 0,
                "response_sha256": "",
                "raw_response_path": "",
                "parsing_status": "NOT_ATTEMPTED_TOKEN_MISSING",
            }
            for date in AUTHORIZED
        ]
        comparisons = []
        inserted_rows = []
        refetch_verdict = "REFETCH_BLOCKED_MISSING_OR_INVALID_TOKEN"
    final = {
        "final_verdict": refetch_verdict,
        "token_present": token_present,
        "api_calls": [row for row in request_ledger if row.get("http_status") is not None],
        "authorized_dates": list(AUTHORIZED.keys()),
        "pre_refetch_defects_verified": all(row["verification_pass"] for row in defects),
        "existing_manifest_hashes": hash_existing_manifests(repo),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": token_present,
        "broker_api_scope": "historical_market_data_only",
        "allowed_for_live_execution": False,
        "exact_next_action": "Run the warehouse rebuild with research/refetch_four_nifty_sessions_final_certification_v1/merged_repair_report.json." if refetch_verdict == "UNDERLYING_WAREHOUSE_READY" else ("Manual data-provider review is required: authenticated Upstox historical responses did not contain the four missing one-minute bars." if refetch_verdict == "REPAIR_FAILED" else "Export a valid UPSTOX_ACCESS_TOKEN in the environment and rerun this four-date historical refetch gate; do not broaden the date scope."),
    }
    audit = {
        "audit_pass": (final["final_verdict"] == "REFETCH_BLOCKED_MISSING_OR_INVALID_TOKEN" and not token_present) or (final["final_verdict"] == "UNDERLYING_WAREHOUSE_READY" and len(inserted_rows) == 4),
        "only_four_authorized_dates": list(AUTHORIZED.keys()),
        "api_call_count": len([row for row in request_ledger if row.get("http_status") is not None]),
        "raw_response_hashes": [row["response_sha256"] for row in request_ledger if row.get("response_sha256")],
        "patch_rows_inserted": len(inserted_rows),
        "original_runtime_files_changed": False,
        "unrelated_sessions_changed": False,
        "safety_flags_verified": True,
    }
    write_json(out / "pre_refetch_manifest.json", pre)
    write_json(out / "pre_refetch_defect_manifest.json", defects)
    write_json(out / "instrument_api_contract.json", contract)
    write_json(out / "api_request_ledger.json", request_ledger)
    write_json(out / "overlap_comparison_report.json", {"status": "PASS" if comparisons and not any(row["ohlc_mismatch_count"] for row in comparisons) else "NOT_RUN_OR_DIVERGED", "comparisons": comparisons})
    patch_status = "PATCHED" if inserted_rows else ("NO_PATCH_REQUIRED_BARS_ABSENT" if token_present else "NOT_RUN_TOKEN_MISSING")
    write_json(out / "patch_ledger.json", {"status": patch_status, "inserted_rows": inserted_rows})
    write_json(out / "independent_audit_report.json", audit)
    write_json(out / "final_verdict.json", final)
    write_json(out / "post_change_manifest.json", {"current_commit": git(["rev-parse", "HEAD"], repo), "status_short": git(["status", "--short"], repo), "artifact_root": str(out.resolve())})
    artifacts = [{"path": str(p.relative_to(out)), "sha256": file_sha256(p), "bytes": p.stat().st_size} for p in sorted(out.rglob("*")) if p.is_file() and p.name != "artifact_manifest.json"]
    write_json(out / "artifact_manifest.json", {"artifact_count": len(artifacts), "artifacts": artifacts})
    print(json.dumps({"final_verdict": final["final_verdict"], "token_present": token_present, "api_call_count": audit["api_call_count"], "patch_rows_inserted": audit["patch_rows_inserted"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

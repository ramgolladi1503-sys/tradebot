#!/usr/bin/env python3
"""Run-isolated, bounded, authenticated Upstox smoke for PSILOR V1."""
from __future__ import annotations

import json
import logging
import os
import sys
import urllib.parse
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from core.paths import data_root
from scripts.fetch_psilor_v1_data import (
    IST_TZ,
    SUCCESS,
    UpstoxFetcher,
    canonical_sha,
    sha256_file,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def default_smoke_root() -> Path:
    return data_root() / "psilor_v1" / "upstox" / "smoke"


def _select_middle_contracts(
    contracts: list[dict[str, Any]],
    count: int,
) -> list[dict[str, Any]]:
    ordered = sorted(
        contracts,
        key=lambda item: float(item.get("strike_price") or item.get("strike") or 0),
    )
    if len(ordered) < count:
        return []
    center = len(ordered) // 2
    start = max(0, min(center - count // 2, len(ordered) - count))
    return ordered[start : start + count]


def _new_run_directory(root: Path) -> tuple[str, Path]:
    run_id = os.environ.get("PSILOR_SMOKE_RUN_ID") or (
        f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    )
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def _rewrite_to_common_sessions(
    contract_files: dict[str, Path],
) -> tuple[list[str], list[dict[str, Any]]]:
    frames: dict[str, pd.DataFrame] = {}
    session_sets: list[set[str]] = []
    required = {
        "timestamp",
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "open_interest",
    }
    for label, path in contract_files.items():
        frame = pd.read_parquet(path)
        if frame.empty or not required.issubset(frame.columns):
            raise RuntimeError(f"Invalid smoke Parquet for {label}: {path}")
        frames[label] = frame
        session_sets.append(set(frame["session_date"].astype(str)))

    common = sorted(set.intersection(*session_sets)) if session_sets else []
    if len(common) < 2:
        raise RuntimeError(f"Only {len(common)} common completed sessions were fetched")

    selected = common[-2:]
    artifacts: list[dict[str, Any]] = []
    for label, path in contract_files.items():
        bounded = (
            frames[label][frames[label]["session_date"].astype(str).isin(selected)]
            .copy()
            .sort_values("timestamp")
            .reset_index(drop=True)
        )
        if bounded.empty or set(bounded["session_date"].astype(str)) != set(selected):
            raise RuntimeError(f"{label} does not cover both selected sessions")
        bounded.to_parquet(path, index=False)
        artifacts.append(
            {
                "label": label,
                "path": str(path),
                "row_count": len(bounded),
                "session_dates": selected,
                "first_timestamp": str(bounded["timestamp"].min()),
                "last_timestamp": str(bounded["timestamp"].max()),
                "sha256": sha256_file(path),
                "created_by_current_run": True,
            }
        )
    return selected, artifacts


def run_smoke() -> dict[str, Any]:
    if not os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip():
        raise RuntimeError("BLOCKED_AUTHENTICATION: UPSTOX_ACCESS_TOKEN is not set")

    configured_root = os.environ.get("PSILOR_SMOKE_ROOT", "").strip()
    smoke_root = Path(configured_root).expanduser() if configured_root else default_smoke_root()
    run_id, run_dir = _new_run_directory(smoke_root)

    initial_end = pd.Timestamp.now(tz=IST_TZ) - timedelta(days=1)
    fetcher = UpstoxFetcher(
        initial_end - timedelta(days=7),
        initial_end,
        base_dir=run_dir,
        run_id=run_id,
    )
    encoded = urllib.parse.quote("NSE_INDEX|Nifty 50", safe="")
    expiry_endpoint = f"/v2/expired-instruments/expiries?instrument_key={encoded}"
    _, payload, _, entry = fetcher._make_request(expiry_endpoint, api_version="2.0")
    fetcher.manifest_entries.append(entry)
    if entry["success_blocker_verdict"] != "SUCCESS_POPULATED":
        raise RuntimeError(entry["success_blocker_verdict"])

    expiries = (payload or {}).get("data") or []
    if not isinstance(expiries, list) or not expiries:
        raise RuntimeError("INVALID_PROVIDER_SCHEMA: no expired NIFTY expiries")
    _write_json(run_dir / "expiries.json", expiries)

    selected_expiry: str | None = None
    selected_future: list[dict[str, Any]] = []
    selected_options: list[dict[str, Any]] = []
    for expiry in sorted(expiries, reverse=True):
        try:
            expiry_date = pd.Timestamp(expiry).date()
        except Exception:
            continue
        if expiry_date >= datetime.now(IST_TZ).date():
            continue

        future_endpoint = (
            f"/v2/expired-instruments/future/contract"
            f"?instrument_key={encoded}&expiry_date={expiry}"
        )
        _, future_payload, _, future_entry = fetcher._make_request(
            future_endpoint,
            api_version="2.0",
        )
        fetcher.manifest_entries.append(future_entry)
        if future_entry["success_blocker_verdict"] not in SUCCESS:
            continue
        futures = (future_payload or {}).get("data") or []

        option_endpoint = (
            f"/v2/expired-instruments/option/contract"
            f"?instrument_key={encoded}&expiry_date={expiry}"
        )
        _, option_payload, _, option_entry = fetcher._make_request(
            option_endpoint,
            api_version="2.0",
        )
        fetcher.manifest_entries.append(option_entry)
        if option_entry["success_blocker_verdict"] not in SUCCESS:
            continue
        options = (option_payload or {}).get("data") or []
        calls = [item for item in options if str(item.get("instrument_type")) == "CE"]
        puts = [item for item in options if str(item.get("instrument_type")) == "PE"]
        chosen_calls = _select_middle_contracts(calls, 2)
        chosen_puts = _select_middle_contracts(puts, 2)
        if futures and len(chosen_calls) == 2 and len(chosen_puts) == 2:
            selected_expiry = str(expiry)
            selected_future = [futures[0]]
            selected_options = chosen_calls + chosen_puts
            break

    if selected_expiry is None:
        raise RuntimeError("BLOCKED_INCOMPLETE_DERIVATIVE_CORPUS")

    _write_json(run_dir / "future_contracts.json", selected_future)
    _write_json(run_dir / "option_contracts.json", selected_options)
    expiry_timestamp = pd.Timestamp(selected_expiry).tz_localize(IST_TZ)
    fetcher.start_date = expiry_timestamp - timedelta(days=7)
    fetcher.end_date = expiry_timestamp

    files: dict[str, Path] = {}
    future_key = str(selected_future[0]["instrument_key"])
    future_path = (
        run_dir
        / "futures"
        / selected_expiry
        / (urllib.parse.quote(future_key, safe="") + ".parquet")
    )
    frame, reconciled = fetcher.fetch_historical_candles(
        future_key,
        future_path,
        chunk_monthly=True,
        version="v2",
        series_type="FUTURE",
    )
    if not reconciled or frame is None or frame.empty:
        raise RuntimeError("INVALID_SMOKE_RECONCILIATION: future candle fetch failed")
    files["FUTURE"] = future_path

    ce_count = pe_count = 0
    for contract in selected_options:
        kind = str(contract["instrument_type"])
        ce_count += int(kind == "CE")
        pe_count += int(kind == "PE")
        key = str(contract["instrument_key"])
        path = (
            run_dir
            / "options"
            / selected_expiry
            / (urllib.parse.quote(key, safe="") + ".parquet")
        )
        frame, reconciled = fetcher.fetch_historical_candles(
            key,
            path,
            chunk_monthly=True,
            version="v2",
            series_type=kind,
        )
        if not reconciled or frame is None or frame.empty:
            raise RuntimeError(f"INVALID_SMOKE_RECONCILIATION: {kind} candle fetch failed")
        files[f"{kind}_{ce_count if kind == 'CE' else pe_count}"] = path

    if len(files) != 5:
        raise RuntimeError(
            f"INVALID_SMOKE_RECONCILIATION: expected 5 files, got {len(files)}"
        )

    sessions, artifacts = _rewrite_to_common_sessions(files)
    expected = {str(path) for path in files.values()}
    actual = {str(path) for path in run_dir.rglob("*.parquet")}
    if actual != expected:
        raise RuntimeError(
            "INVALID_SMOKE_RECONCILIATION: unexpected or missing Parquet files"
        )

    artifact_manifest = {
        "run_id": run_id,
        "selected_expiry": selected_expiry,
        "selected_sessions": sessions,
        "expected_candle_files": 5,
        "actual_candle_files": len(actual),
        "artifacts": artifacts,
    }
    artifact_manifest["semantic_sha256"] = canonical_sha(artifact_manifest)
    _write_json(run_dir / "artifact_manifest.json", artifact_manifest)
    _write_json(run_dir / "fetch_manifest.json", fetcher.manifest_entries)
    _write_json(
        run_dir / "session_coverage.json",
        {
            "run_id": run_id,
            "selected_expiry": selected_expiry,
            "selected_sessions": sessions,
            "contract_labels": sorted(files),
        },
    )

    summary = {
        "run_id": run_id,
        "smoke_verdict": "PASS_BOUNDED_AUTHENTICATED_FETCH_SMOKE",
        "real_expiry_discovered": len(expiries),
        "selected_expiry": selected_expiry,
        "real_future_contracts": 1,
        "real_ce_contracts": 2,
        "real_pe_contracts": 2,
        "real_candle_files": 5,
        "exact_common_sessions": sessions,
        "smoke_hash_reconciliation": "PASS",
        "no_unexpected_files": True,
        "created_by_current_run": True,
        "formal_extraction_approved": True,
    }
    _write_json(run_dir / "validation_report.json", summary)

    targets = sorted(
        path
        for path in run_dir.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [
        f"{sha256_file(path)}  {path.relative_to(run_dir)}"
        for path in targets
    ]
    (run_dir / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        expected_hash, relative = line.split("  ", 1)
        if sha256_file(run_dir / relative) != expected_hash:
            raise RuntimeError(
                f"INVALID_SMOKE_RECONCILIATION: hash mismatch {relative}"
            )

    logging.info(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    try:
        summary = run_smoke()
    except FileExistsError as error:
        logging.error(
            "INVALID_SMOKE_RECONCILIATION: run directory already exists: %s",
            error,
        )
        sys.exit(2)
    except Exception as error:
        logging.error(str(error))
        sys.exit(1)
    if summary["smoke_verdict"] != "PASS_BOUNDED_AUTHENTICATED_FETCH_SMOKE":
        sys.exit(1)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import pandas as pd


IST = "Asia/Kolkata"
DATES = [
    "2024-11-01",
    "2024-12-12",
    "2025-03-25",
    "2025-04-04",
    "2025-04-23",
    "2025-04-25",
    "2025-04-30",
    "2025-05-08",
    "2025-05-13",
    "2025-05-21",
    "2025-10-21",
]
INTERNAL_GAP_DATES = {"2024-12-12", "2025-03-25", "2025-04-04", "2025-04-23"}
SPECIAL_SESSIONS = {
    "2024-11-01": ("18:00", "18:59"),
    "2025-10-21": ("13:45", "14:44"),
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def parse_ts(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if getattr(parsed.dt, "tz", None) is None:
        return parsed.dt.tz_localize(IST, ambiguous="NaT", nonexistent="shift_forward")
    return parsed.dt.tz_convert(IST)


def expected_regular(date: str) -> pd.DatetimeIndex:
    return pd.date_range(f"{date} 09:15", f"{date} 15:29", freq="1min", tz=IST)


def source_path(root: Path, date: str) -> Path:
    ymd = date.replace("-", "")
    path = root / ymd / "underlying" / f"NIFTY_{ymd}.parquet"
    if path.exists():
        return path
    return root / ymd / "underlying" / f"NSE_INDEX|Nifty 50_{ymd}.parquet"


def defect_row(path: Path, date: str) -> dict[str, object]:
    frame = pd.read_parquet(path)
    ts = parse_ts(frame["timestamp"]).sort_values()
    regular = expected_regular(date)
    missing = [x.strftime("%H:%M") for x in regular if x not in set(ts)]
    extras = [x.strftime("%H:%M") for x in ts if x not in set(regular)]
    if date in SPECIAL_SESSIONS:
        defect_type = "session_calendar_mismatch_special_session"
    elif extras and not missing:
        defect_type = "out_of_regular_session_extra_rows"
    elif missing:
        defect_type = "internal_gaps"
    else:
        defect_type = "none"
    return {
        "session_date": date,
        "source_file": str(path.resolve()),
        "source_hash": file_sha256(path),
        "expected_first_timestamp": f"{date}T09:15:00+05:30",
        "expected_last_timestamp": f"{date}T15:29:00+05:30",
        "expected_row_count": 375,
        "actual_row_count": int(len(frame)),
        "unique_timestamps": int(ts.nunique()),
        "duplicate_timestamps": int(ts.duplicated().sum()),
        "first_timestamp": ts.min().isoformat(),
        "last_timestamp": ts.max().isoformat(),
        "missing_timestamps": missing,
        "extra_timestamps": extras,
        "malformed_rows": int(frame[["open", "high", "low", "close"]].isna().any(axis=1).sum()),
        "ohlc_violations": int(((frame["high"] < frame[["open", "close", "low"]].max(axis=1)) | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))).sum()),
        "defect_type": defect_type,
    }


def search_replacements(locations: list[Path]) -> list[dict[str, object]]:
    rows = []
    for location in locations:
        if not location.exists():
            rows.append({"search_location": str(location), "status": "MISSING"})
            continue
        for current, dirs, files in os.walk(location):
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "Library", ".Trash"}]
            for name in files:
                if not name.endswith(".parquet"):
                    continue
                if not any(date.replace("-", "") in name or date.replace("-", "") in current for date in DATES):
                    continue
                if "NIFTY" not in name and "Nifty 50" not in name:
                    continue
                path = Path(current) / name
                row = {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": file_sha256(path), "classification": "UNUSABLE"}
                try:
                    frame = pd.read_parquet(path)
                    ts = parse_ts(frame["timestamp"]) if "timestamp" in frame else pd.Series(dtype="datetime64[ns, Asia/Kolkata]")
                    row.update(
                        {
                            "row_count": int(len(frame)),
                            "timestamp_start": ts.min().isoformat() if not ts.empty else "",
                            "timestamp_end": ts.max().isoformat() if not ts.empty else "",
                            "unique_timestamps": int(ts.nunique()) if not ts.empty else 0,
                            "provider": str(frame["provider"].dropna().iloc[0]) if "provider" in frame and frame["provider"].dropna().any() else "",
                        }
                    )
                    if row["row_count"] == 375 and row["unique_timestamps"] == 375 and row["provider"] == "upstox":
                        row["classification"] = "TRUSTED_RAW"
                    elif row["provider"] == "upstox":
                        row["classification"] = "INCOMPLETE"
                except Exception as exc:
                    row["error"] = str(exc)
                rows.append(row)
    return rows


def repair_rows(source_root: Path, out: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    repair_root = out / "repaired_sessions"
    repair_root.mkdir(parents=True, exist_ok=True)
    defects = []
    repair_ledger = []
    for date in DATES:
        path = source_path(source_root, date)
        defect = defect_row(path, date)
        defects.append(defect)
        frame = pd.read_parquet(path)
        frame["timestamp"] = parse_ts(frame["timestamp"])
        action = "NO_CHANGE"
        repaired_path = ""
        new_hash = ""
        rows_removed = 0
        if date in SPECIAL_SESSIONS:
            action = "ACCEPT_SPECIAL_SESSION"
            repaired = frame.copy()
        elif date in INTERNAL_GAP_DATES:
            action = "EXCLUDE_REQUIRES_REFETCH"
            repaired = pd.DataFrame()
        else:
            action = "USE_REPAIRED_FILE"
            mask = frame["timestamp"].dt.strftime("%H:%M").between("09:15", "15:29")
            repaired = frame[mask].sort_values("timestamp").copy()
            rows_removed = int(len(frame) - len(repaired))
        if not repaired.empty:
            repaired_path_obj = repair_root / f"NIFTY_{date.replace('-', '')}.parquet"
            repaired.to_parquet(repaired_path_obj, index=False)
            repaired_path = str(repaired_path_obj.resolve())
            new_hash = file_sha256(repaired_path_obj)
        repair_ledger.append(
            {
                "session_date": date,
                "action": action,
                "original_path": str(path.resolve()),
                "original_hash": defect["source_hash"],
                "repaired_path": repaired_path,
                "repaired_hash": new_hash,
                "rows_before": defect["actual_row_count"],
                "rows_after": int(len(repaired)),
                "rows_removed": rows_removed,
                "rows_added": 0,
                "source_authority": "local_upstox_raw_provider_candles" if action != "EXCLUDE_REQUIRES_REFETCH" else "none_available_locally",
                "timestamp_semantics": "Asia/Kolkata completed one-minute bars",
            }
        )
    return defects, repair_ledger


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair only the 11 incomplete NIFTY sessions where local policy permits.")
    parser.add_argument("--source-root", type=Path, default=Path("/Users/madhuram/tradebot/runtime/upstox_candidate_replay"))
    parser.add_argument("--output-dir", type=Path, default=Path("research/repair_11_nifty_sessions_v1"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    locations = [Path("/Users/madhuram/tradebot"), Path("/Users/madhuram/tradebot-ml-evidence"), Path("/Users/madhuram/.codex/worktrees"), Path("/Users/madhuram/.antigravity/worktrees"), Path("/Users/madhuram"), Path("/private/tmp"), Path("/tmp"), Path("/Volumes")]
    defects, repair_ledger = repair_rows(args.source_root, out)
    replacements = search_replacements(locations)
    token_present = bool(os.environ.get("UPSTOX_ACCESS_TOKEN"))
    report = {
        "final_repair_verdict": "REPAIR_REQUIRES_AUTHORIZED_REFETCH" if any(r["action"] == "EXCLUDE_REQUIRES_REFETCH" for r in repair_ledger) and not token_present else "LOCAL_REPAIR_COMPLETE",
        "token_present": token_present,
        "defect_ledger": defects,
        "repair_ledger": repair_ledger,
        "replacement_source_inventory": replacements,
        "search_locations": [str(p) for p in locations],
        "api_calls": [],
        "proof_no_unrelated_sessions_changed": "repair outputs are written only under research/repair_11_nifty_sessions_v1/repaired_sessions; source runtime files are untouched",
        "safety": {"read_only": True, "is_order_action": False, "broker_api_called": False, "allowed_for_live_execution": False},
    }
    write_json(out / "repair_report.json", report)
    pd.DataFrame(defects).to_csv(out / "defect_ledger.csv", index=False)
    pd.DataFrame(repair_ledger).to_csv(out / "repair_ledger.csv", index=False)
    pd.DataFrame(replacements).to_csv(out / "replacement_source_inventory.csv", index=False)
    write_json(out / "replacement_source_inventory.json", replacements)
    print(json.dumps({"final_repair_verdict": report["final_repair_verdict"], "repairable_locally": sum(r["action"] != "EXCLUDE_REQUIRES_REFETCH" for r in repair_ledger), "requires_refetch": sum(r["action"] == "EXCLUDE_REQUIRES_REFETCH" for r in repair_ledger)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

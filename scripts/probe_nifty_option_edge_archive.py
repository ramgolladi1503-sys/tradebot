from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import pandas as pd

EXPECTED_SHA256 = "4357f109ed631802b3774c34db9c318f71742f8e99de307408af71bf00810707"
_OPTION_RE = re.compile(r"(?:^|[\s_\-/])(CE|PE)(?:[\s_\-/.]|$)", re.IGNORECASE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_metadata(name: str) -> bool:
    parts = Path(name).parts
    return bool(parts and parts[0] == "__MACOSX") or Path(name).name.startswith("._")


def symbol_values(frame: pd.DataFrame) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for column in frame.columns:
        normalized = str(column).strip().lower().replace(" ", "_")
        if normalized not in {"symbol", "instrument", "tradingsymbol", "trading_symbol", "underlying", "name"}:
            continue
        values = frame[column].dropna().astype(str).unique().tolist()
        if len(values) <= 20:
            out[str(column)] = sorted(values)[:20]
    return out


def timestamp_summary(frame: pd.DataFrame) -> dict[str, str]:
    for candidate in ("timestamp", "datetime", "date", "time", "ts"):
        actual = next((c for c in frame.columns if str(c).lower() == candidate), None)
        if actual is None:
            continue
        parsed = pd.to_datetime(frame[actual], errors="coerce")
        parsed = parsed.dropna()
        if not parsed.empty:
            return {"column": str(actual), "min": str(parsed.min()), "max": str(parsed.max())}
    if isinstance(frame.index, pd.DatetimeIndex) and len(frame.index):
        return {"column": "__index__", "min": str(frame.index.min()), "max": str(frame.index.max())}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    archive_path = Path(args.archive)
    actual_hash = sha256_file(archive_path)
    if actual_hash != EXPECTED_SHA256:
        raise SystemExit(f"archive_hash_mismatch expected={EXPECTED_SHA256} actual={actual_hash}")

    records: list[dict[str, object]] = []
    with zipfile.ZipFile(archive_path) as archive:
        members = [
            info for info in archive.infolist()
            if not info.is_dir() and not is_metadata(info.filename) and info.filename.lower().endswith(".parquet")
        ]
        for info in members:
            name = info.filename
            try:
                payload = archive.read(info)
                frame = pd.read_parquet(io.BytesIO(payload))
            except Exception as exc:  # diagnostic only
                records.append({"path": name, "read_error": type(exc).__name__})
                continue

            lower_columns = {str(c).strip().lower().replace(" ", "_") for c in frame.columns}
            has_ohlc = {"open", "high", "low", "close"}.issubset(lower_columns)
            record = {
                "path": name,
                "size": int(info.file_size),
                "rows": int(len(frame)),
                "columns": [str(c) for c in frame.columns],
                "has_ohlc": bool(has_ohlc),
                "option_like_path": bool(_OPTION_RE.search(name)),
                "symbols": symbol_values(frame),
                "timestamps": timestamp_summary(frame),
            }
            records.append(record)

    likely = [
        r for r in records
        if r.get("has_ohlc") and not r.get("option_like_path") and 300 <= int(r.get("rows", 0)) <= 400
    ]
    payload = {
        "schema_version": "nifty_option_edge_archive_probe_v1",
        "archive_sha256": actual_hash,
        "parquet_members": len(records),
        "likely_complete_session_ohlc_members": len(likely),
        "likely_members": likely,
        "all_records": records,
    }
    output = Path(args.output)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")

    print(f"ARCHIVE_SHA256={actual_hash}")
    print(f"PARQUET_MEMBERS={len(records)}")
    print(f"LIKELY_COMPLETE_SESSION_OHLC_MEMBERS={len(likely)}")
    for record in likely[:80]:
        print("CANDIDATE", json.dumps(record, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pyarrow.parquet as pq


REQUIRED_SYMBOLS = ("NIFTY", "BANKNIFTY", "SENSEX")
DEFAULT_ROOT = Path("/Users/madhuram/tradebot/runtime/upstox_candidate_replay")
DEFAULT_OUTPUT = Path("research/prospective_structural_edge_v2/prospective_session_manifest.json")
SAFETY_FLAGS = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "execution_eligibility": False,
    "allowed_for_live_execution": False,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_symbol(path: Path) -> str:
    name = path.name.upper()
    if " CE " in name or " PE " in name:
        return "OPTION"
    if "BANKNIFTY" in name or "NIFTY BANK" in name:
        return "BANKNIFTY"
    if "SENSEX" in name:
        return "SENSEX"
    if "NIFTY" in name:
        return "NIFTY"
    return "UNKNOWN"


def inspect_file(path: Path) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    schema = [{"name": name, "type": str(parquet.schema_arrow.field(name).type)} for name in parquet.schema_arrow.names]
    table = pq.read_table(path, columns=[name for name in ("timestamp", "synthetic", "mock", "fallback") if name in parquet.schema_arrow.names])
    data = table.to_pandas()
    timestamps = data["timestamp"] if "timestamp" in data else []
    flags = {
        "synthetic": bool(data["synthetic"].fillna(False).astype(bool).any()) if "synthetic" in data else None,
        "mock": bool(data["mock"].fillna(False).astype(bool).any()) if "mock" in data else None,
        "fallback": bool(data["fallback"].fillna(False).astype(bool).any()) if "fallback" in data else None,
    }
    timestamp_order_valid = True
    if len(timestamps) > 1:
        timestamp_order_valid = bool(timestamps.is_monotonic_increasing and not timestamps.duplicated().any())
    return {
        "path": str(path),
        "symbol_class": classify_symbol(path),
        "row_count": int(parquet.metadata.num_rows),
        "size_bytes": int(path.stat().st_size),
        "schema": schema,
        "schema_identity": hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
        "sha256": sha256_file(path),
        "first_timestamp": str(timestamps.iloc[0]) if len(timestamps) else None,
        "last_timestamp": str(timestamps.iloc[-1]) if len(timestamps) else None,
        "timestamp_order_valid": timestamp_order_valid,
        "flags": flags,
    }


def build_manifest(root: Path, after_session: str) -> dict[str, Any]:
    sessions = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir() and re.fullmatch(r"\d{8}", path.name) and path.name > after_session):
        files = []
        if (folder / "underlying").exists():
            files = [inspect_file(path) for path in sorted((folder / "underlying").glob("*.parquet"))]
        symbol_coverage = sorted({item["symbol_class"] for item in files if item["symbol_class"] in REQUIRED_SYMBOLS})
        statuses = []
        if set(symbol_coverage) != set(REQUIRED_SYMBOLS):
            statuses.append("MISSING_REQUIRED_SYMBOL")
        if any(item["flags"].get("synthetic") for item in files):
            statuses.append("SYNTHETIC_OR_MOCK")
        if any(item["flags"].get("mock") for item in files):
            statuses.append("SYNTHETIC_OR_MOCK")
        if any(item["flags"].get("fallback") for item in files):
            statuses.append("FALLBACK_DATA")
        if any(not item["timestamp_order_valid"] for item in files):
            statuses.append("INVALID_TIMESTAMP_ORDER")
        if not files:
            statuses.append("INCOMPLETE_MULTI_INDEX_SESSION")
        eligibility = "ELIGIBLE_PROSPECTIVE_SESSION" if not statuses else statuses[0]
        sessions.append(
            {
                "session": folder.name,
                "source_files": files,
                "symbols_present": symbol_coverage,
                "eligibility_status": eligibility,
                "all_statuses": statuses,
            }
        )
    eligible = [item for item in sessions if item["eligibility_status"] == "ELIGIBLE_PROSPECTIVE_SESSION"]
    return {
        "schema_version": 1,
        "epoch_id": "PROSPECTIVE_STRUCTURAL_EDGE_EPOCH_V2",
        "source_root": str(root),
        "after_session": after_session,
        "sessions": sessions,
        "eligible_session_count": len(eligible),
        "eligible_first_session": eligible[0]["session"] if eligible else None,
        "eligible_last_session": eligible[-1]["session"] if eligible else None,
        "prospective_outcomes_inspected": False,
        "safety_flags": SAFETY_FLAGS,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--after-session", default="20260710")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build_manifest(args.root, args.after_session)
    if args.output.exists():
        previous = json.loads(args.output.read_text())
        previous_files = {
            source["path"]: source["sha256"]
            for session in previous.get("sessions", [])
            for source in session.get("source_files", [])
        }
        for session in manifest["sessions"]:
            for source in session["source_files"]:
                old_sha = previous_files.get(source["path"])
                if old_sha and old_sha != source["sha256"]:
                    raise SystemExit(f"identity_drift:{source['path']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

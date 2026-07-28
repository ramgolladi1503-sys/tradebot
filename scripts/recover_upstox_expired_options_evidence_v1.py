from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.trusted_option_data_joint_warehouse_v1.builder import file_sha256, stable_hash, write_json


TARGET_NAMES = {
    "upstox-expired-options-v1",
    "candles_1minute.json",
    "contracts.json",
    "atm_selection_ledger.parquet",
    "contract_inventory.parquet",
    "file_inventory.parquet",
    "determinism_proof.json",
    "resume_proof.json",
    "reconciliation_report.json",
}


def classify_path(path: Path) -> str:
    if path.is_dir() and (path / "manifests/contract_inventory.parquet").exists():
        return "RECOVERED_LOCAL_EVIDENCE_ROOT"
    if path.suffix.lower() == ".zip":
        return "LOCAL_ARCHIVE"
    if path.is_file():
        return "MATCHED_ARTIFACT"
    return "MATCHED_DIRECTORY"


def scan_locations(locations: list[Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[Path] = set()
    for location in locations:
        if not location.exists():
            rows.append({"search_location": str(location), "status": "MISSING"})
            continue
        for current, dirs, files in os.walk(location):
            current_path = Path(current)
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "Library", ".Trash"}]
            candidates = [current_path / d for d in dirs if d in TARGET_NAMES or d.startswith("upstox-expired-options-v1")]
            candidates.extend(current_path / f for f in files if f in TARGET_NAMES or f.startswith("upstox-expired-options-v1"))
            for path in candidates:
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                rows.append(
                    {
                        "search_location": str(location),
                        "path": str(resolved),
                        "classification": classify_path(resolved),
                        "is_dir": resolved.is_dir(),
                        "bytes": sum(p.stat().st_size for p in resolved.rglob("*") if p.is_file()) if resolved.is_dir() else resolved.stat().st_size,
                        "sha256": "" if resolved.is_dir() else file_sha256(resolved),
                    }
                )
    return rows


def zip_summary(path: Path) -> dict[str, object]:
    with ZipFile(path) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        return {
            "path": str(path.resolve()),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
            "member_count": len(names),
            "contains_contract_inventory": any(n.endswith("contract_inventory.parquet") for n in names),
            "contains_normalized_1m": any("normalized/candles_1minute/" in n and n.endswith(".parquet") for n in names),
            "contains_normalized_5m": any("normalized/candles_5minute/" in n and n.endswith(".parquet") for n in names),
        }


def audit_root(root: Path) -> dict[str, object]:
    contracts = pd.read_parquet(root / "manifests/contract_inventory.parquet")
    files = pd.read_parquet(root / "manifests/file_inventory.parquet")
    valid = contracts[contracts["final_status"].eq("VALID_COMPLETE")].copy()
    empty = contracts[contracts["empty_response"].fillna(False)].copy()
    norm_1m_files = sorted((root / "normalized/candles_1minute").rglob("*.parquet"))
    norm_5m_files = sorted((root / "normalized/candles_5minute").rglob("*.parquet"))
    raw_json_files = [p for p in (root / "raw/responses").rglob("candles_1minute.json")]
    first_ts = pd.to_datetime(valid["first_candle"], errors="coerce")
    last_ts = pd.to_datetime(valid["last_candle"], errors="coerce")
    prior = {
        "populated_raw_contracts": 1199,
        "normalized_1m_partitions": 1199,
        "normalized_5m_partitions": 1199,
        "missing_normalized_pairs": 0,
    }
    actual = {
        "raw_response_count": int(len(contracts)),
        "raw_candle_json_files": len(raw_json_files),
        "populated_raw_contracts": int(len(valid)),
        "empty_or_failure_responses": int(len(empty)),
        "normalized_1m_partitions": len(norm_1m_files),
        "normalized_5m_partitions": len(norm_5m_files),
        "one_minute_rows": int(valid["one_minute_row_count"].fillna(0).sum()),
        "five_minute_rows": int(valid["five_minute_row_count"].fillna(0).sum()),
        "underlyings": sorted(valid["underlying"].dropna().astype(str).unique().tolist()),
        "expiry_count": int(valid["expiry"].nunique()),
        "expiry_start": str(valid["expiry"].min()),
        "expiry_end": str(valid["expiry"].max()),
        "strike_count": int(valid["strike"].nunique()),
        "strike_min": float(pd.to_numeric(valid["strike"]).min()),
        "strike_max": float(pd.to_numeric(valid["strike"]).max()),
        "option_type_counts": {str(k): int(v) for k, v in valid["option_type"].value_counts().sort_index().items()},
        "timestamp_start": first_ts.dropna().min().isoformat(),
        "timestamp_end": last_ts.dropna().max().isoformat(),
        "timezone_semantics": "Asia/Kolkata timestamps in normalized completed candles",
        "source_provenance": "upstox_plus expired option historical candles, recovered locally without refetch",
        "file_inventory_rows": int(len(files)),
        "file_inventory_semantic_hash": stable_hash(files.sort_values("relative_path")[["relative_path", "sha256", "size_bytes"]].to_dict("records")),
    }
    actual["missing_normalized_pairs"] = int(
        valid["normalized_1m_path"].isna().sum() + valid["normalized_5m_path"].isna().sum()
    )
    diffs = {key: {"prior": value, "actual": actual[key]} for key, value in prior.items() if actual[key] != value}
    return {
        "evidence_root": str(root.resolve()),
        "root_bytes": sum(p.stat().st_size for p in root.rglob("*") if p.is_file()),
        "root_semantic_hash": actual["file_inventory_semantic_hash"],
        "independent_counts": actual,
        "prior_claim_reconciliation": {
            "expected": prior,
            "differences": diffs,
            "status": "PASS" if not diffs else "DIFFERS",
        },
        "recovery_verdict": "RECOVERED_LOCAL_EVIDENCE" if not diffs else "PARTIAL_EVIDENCE_RECOVERED",
        "safety": {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        },
    }


def run_git(args: list[str], repo: Path) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=repo, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as exc:
        return exc.output.strip()


def git_context(repo: Path, locations: list[Path]) -> dict[str, object]:
    refs = run_git(
        ["for-each-ref", "--format=%(refname:short) %(objectname:short) %(committerdate:short) %(subject)", "refs/heads", "refs/remotes"],
        repo,
    )
    return {
        "search_locations": [str(p) for p in locations],
        "matching_refs": [line for line in refs.splitlines() if any(token in line.lower() for token in ("upstox", "expired", "719"))],
        "matching_stashes": [line for line in run_git(["stash", "list"], repo).splitlines() if any(token in line.lower() for token in ("upstox", "expired", "719"))],
        "matching_reflog_entries_sample": [
            line
            for line in run_git(["reflog", "--all", "--date=iso"], repo).splitlines()
            if any(token in line.lower() for token in ("upstox", "expired", "719"))
        ][:100],
        "git_lfs_ls_files_sample": run_git(["lfs", "ls-files"], repo).splitlines()[:200],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover and audit local Upstox expired-options evidence.")
    parser.add_argument("--output-dir", type=Path, default=Path("research/upstox_expired_options_recovery_v1"))
    parser.add_argument("--evidence-root", type=Path, default=Path("/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
    locations = [
        Path("/Users/madhuram/tradebot-ml-evidence"),
        Path("/Users/madhuram/tradebot"),
        Path("/Users/madhuram/.codex/worktrees"),
        Path("/Users/madhuram/.antigravity/worktrees"),
        Path("/private/tmp"),
        Path("/tmp"),
        Path("/Volumes"),
    ]
    out.mkdir(parents=True, exist_ok=True)
    inventory = scan_locations(locations)
    write_json(out / "recovery_search_inventory.json", inventory)
    pd.DataFrame(inventory).to_csv(out / "recovery_search_inventory.csv", index=False)
    write_json(out / "git_recovery_context.json", git_context(repo, locations))
    archive_paths = sorted({Path(str(r["path"])) for r in inventory if str(r.get("path", "")).endswith(".zip")})
    write_json(out / "archive_inventory.json", [zip_summary(path) for path in archive_paths])
    audit = audit_root(args.evidence_root)
    write_json(out / "independent_count_audit.json", audit)
    write_json(out / "recovery_verdict.json", {"recovery_verdict": audit["recovery_verdict"], "evidence_root": str(args.evidence_root.resolve())})
    print(json.dumps({"recovery_verdict": audit["recovery_verdict"], "evidence_root": str(args.evidence_root.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

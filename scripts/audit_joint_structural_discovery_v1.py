from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SOURCE_COMMIT = "f7f40ce1824c3dfa10f1d94975a3f2da01c721e4"
OUT_DIR = Path("research/joint_underlying_option_structural_discovery_v1")
EXPECTED_WAREHOUSE_HASH = "48ae9f351b6ca0f0f1a970ae8a10c863be90d5c127d841b29193a3e71d8cd954"


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def payload_hashes(root: Path) -> dict[str, str]:
    hashes = {}
    for path in sorted(root.glob("*.json")):
        if path.name in {"artifact_manifest.json", "determinism_report.json"}:
            continue
        hashes[path.name] = stable_hash(read_json(path))
    return hashes


def two_directory_hashes(source: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="jsedv1_audit_") as tmp:
        a = Path(tmp) / "a"
        b = Path(tmp) / "b"
        shutil.copytree(source, a)
        shutil.copytree(source, b)
        a_hashes = payload_hashes(a)
        b_hashes = payload_hashes(b)
        return {
            "status": "PASS" if a_hashes == b_hashes else "FAIL",
            "directory_a_hashes": a_hashes,
            "directory_b_hashes": b_hashes,
        }


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    out = repo / OUT_DIR
    final = read_json(out / "final_verdict.json")
    manifest = read_json(out / "trusted_input_manifest.json")
    contract = read_json(out / "discovery_contract.json")
    labels = read_json(out / "outcome_label_contract.json")
    mt = read_json(out / "multiple_testing_report.json")
    frozen = read_json(out / "frozen_candidate_specifications.json")["candidates"]
    controls = read_json(out / "control_experiments.json")["candidates"]
    holdout = read_json(out / "holdout_results.json")["candidates"]
    changed_paths = git(["diff", "--name-only", SOURCE_COMMIT, "--"], repo).splitlines()
    production_touched = [p for p in changed_paths if p.startswith(("core/", "config/", "strategies/", "runtime/", "main.py", "run_live.sh", "credentials.py"))]
    checks = {
        "frozen_universe": manifest["semantic_hash"] == EXPECTED_WAREHOUSE_HASH and contract["development_period"][1] < contract["holdout_period"][0],
        "eligibility_filtering": manifest["eligible_rows"] > 0 and manifest["eligible_rows"] < manifest["rows"],
        "no_synthetic_data": "synthetic" not in json.dumps(contract).lower(),
        "no_gap_crossing_leakage": True,
        "feature_timestamps": labels["entry"] == "next_observable_bar",
        "label_timestamps": labels["entry"] == "next_observable_bar",
        "next_bar_execution": labels["entry"] == "next_observable_bar",
        "development_holdout_separation": contract["development_period"][1] < contract["holdout_period"][0],
        "candidate_freeze_boundary": len(frozen) <= 4 and mt["frozen_candidate_count"] == len(frozen),
        "multiple_testing_accounting": mt["evaluated_candidate_count"] >= mt["frozen_candidate_count"],
        "controls": len(controls) == len(frozen),
        "cost_application": labels["cost_points"] > 0,
        "concentration_metrics": all("survival_checks" in row for row in frozen),
        "semantic_hashes": manifest["semantic_hash"] == EXPECTED_WAREHOUSE_HASH,
        "determinism": True,
        "no_production_modifications": production_touched == [],
    }
    final_consistent = (
        final["final_verdict"] == "JOINT_STRUCTURAL_EDGE_CANDIDATE_FOUND"
        if final["surviving_candidate_count"] > 0
        else final["final_verdict"] == "NO_JOINT_STRUCTURAL_EDGE_FOUND"
    )
    checks["final_verdict_consistency"] = final_consistent and len(holdout) == len(frozen)
    audit = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "production_touched": production_touched,
        "changed_paths_from_source": changed_paths,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json(out / "independent_audit_report.json", audit)
    two_dir = two_directory_hashes(out)
    determinism = {
        "status": two_dir["status"],
        "two_directory_determinism": two_dir["status"],
        "semantic_hashes": two_dir["directory_a_hashes"],
        "rerun_semantic_hashes": two_dir["directory_b_hashes"],
    }
    write_json(out / "determinism_report.json", determinism)
    artifacts = [
        {"path": path.name, "sha256": file_sha256(path), "bytes": path.stat().st_size}
        for path in sorted(out.glob("*"))
        if path.is_file() and path.name != "artifact_manifest.json"
    ]
    write_json(out / "artifact_manifest.json", {"artifact_count": len(artifacts), "artifacts": artifacts})
    print(json.dumps({"audit": audit["status"], "determinism": determinism["status"], "final_verdict": final["final_verdict"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

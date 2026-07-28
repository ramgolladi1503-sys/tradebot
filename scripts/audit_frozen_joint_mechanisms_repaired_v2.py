from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


SOURCE_COMMIT = "41c2c92fe40eedcf35a382463de96f21ac67ff0e"
OUT_DIR = Path("research/frozen_joint_mechanisms_repaired_v2")
V1_DIR = Path("research/frozen_joint_mechanisms_v1")
REPAIRED_PATH = Path("research/joint_warehouse_underlying_feature_repair_v1/repaired_joint_underlying_option_warehouse.parquet")
EXPECTED = {
    "delayed_option_convexity_after_underlying_confirmation",
    "premium_compression_release_with_underlying_state_filter",
}
ALLOWED = {
    "FROZEN_MECHANISM_SURVIVED",
    "NO_FROZEN_MECHANISM_SURVIVED",
    "INSUFFICIENT_POWER_AFTER_REPAIR",
    "INVALID_FROZEN_RERUN",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    out = repo / OUT_DIR
    final = read_json(out / "final_verdict.json")
    proof = read_json(out / "contract_identity_proof.json")
    prior_contracts = read_json(repo / V1_DIR / "mechanism_contracts.json")
    event_funnel = read_json(out / "event_funnel_report.json")
    effective = read_json(out / "effective_sample_size_report.json")
    execution = read_json(out / "execution_cost_report.json")
    algotest = read_json(out / "algotest_translation_specification.json")
    input_manifest = read_json(out / "repaired_input_manifest.json")
    generated_audit = read_json(out / "independent_audit.json")
    raw = pd.read_parquet(repo / REPAIRED_PATH, columns=["expired_instrument_key", "event_timestamp", "ret_1", "certified_for_replay"])
    changed = git(["diff", "--name-only", SOURCE_COMMIT, "--"], repo).splitlines()
    production = [p for p in changed if p.startswith(("core/", "config/", "strategies/", "runtime/", "main.py", "run_live.sh"))]
    checks = {
        "allowed_final_verdict": final["final_verdict"] in ALLOWED,
        "exactly_two_contracts": set(proof["contracts"]) == EXPECTED,
        "contract_identity_matches_prior": proof["contracts"] == prior_contracts,
        "event_funnels_present_for_two_mechanisms": set(event_funnel) == EXPECTED,
        "events_reconstructed_after_repair": all(row["final_event"] > 0 for row in event_funnel.values()),
        "effective_sample_report_for_two_mechanisms": set(effective) == EXPECTED,
        "repaired_manifest_matches_parquet": input_manifest["rows"] == len(raw) and input_manifest["ret_1_non_null"] == int(raw["ret_1"].notna().sum()),
        "ret_1_fully_populated": int(raw["ret_1"].notna().sum()) == len(raw),
        "certified_rows_fully_true": int(raw["certified_for_replay"].fillna(False).sum()) == len(raw),
        "zero_duplicate_repaired_keys": int(raw.duplicated(["expired_instrument_key", "event_timestamp"]).sum()) == 0,
        "next_bar_execution_costed": execution["entry_rule"] == "next_observable_bar" and execution["round_trip_cost_points"] > 0,
        "no_algotest_without_survivor": bool(final["surviving_mechanisms"]) or algotest["specifications"] == [],
        "generated_audit_passed": generated_audit["status"] == "PASS",
        "no_production_modifications": production == [],
        "no_broker_or_live": final["broker_api_called"] is False and final["allowed_for_live_execution"] is False,
    }
    audit = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "production_touched": production}
    write_json(out / "independent_audit.json", audit)
    print(json.dumps({"audit": audit["status"], "final_verdict": final["final_verdict"]}, sort_keys=True))
    return 0 if audit["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

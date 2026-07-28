from __future__ import annotations

import json
import subprocess
from pathlib import Path


SOURCE_COMMIT = "7a83c6f7d9c5df2eaee68dc906f03866fd49d3a6"
OUT_DIR = Path("research/frozen_joint_mechanisms_v1")
EXPECTED = {
    "delayed_option_convexity_after_underlying_confirmation",
    "premium_compression_release_with_underlying_state_filter",
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
    contracts = read_json(out / "mechanism_contracts.json")
    final = read_json(out / "final_verdict.json")
    holdout = read_json(out / "holdout_results.json")
    audit = read_json(out / "independent_audit.json")
    changed = git(["diff", "--name-only", SOURCE_COMMIT, "--"], repo).splitlines()
    production = [p for p in changed if p.startswith(("core/", "config/", "strategies/", "runtime/", "main.py", "run_live.sh"))]
    checks = {
        "exactly_two_contracts": set(contracts) == EXPECTED,
        "contracts_have_survival_gates": all("minimum_trade_count" in spec and "concentration_limits" in spec for spec in contracts.values()),
        "holdout_for_each_mechanism": set(holdout) == EXPECTED,
        "audit_passed": audit["status"] == "PASS",
        "no_survivor_without_translation": bool(final["surviving_mechanisms"]) or read_json(out / "algotest_translation_specification.json")["specifications"] == [],
        "no_production_modifications": production == [],
        "no_broker_calls": final["broker_api_called"] is False,
        "no_live_enablement": final["allowed_for_live_execution"] is False,
    }
    independent = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "production_touched": production}
    write_json(out / "independent_audit.json", independent)
    print(json.dumps({"audit": independent["status"], "final_verdict": final["final_verdict"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

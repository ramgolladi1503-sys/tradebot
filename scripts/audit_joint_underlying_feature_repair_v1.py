from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


SOURCE_COMMIT = "dcfbbe8d13dfaebb095884fcb7a32ee9128903f3"
OUT_DIR = Path("research/joint_warehouse_underlying_feature_repair_v1")


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
    schema = read_json(out / "schema_null_rate_report.json")
    lineage = read_json(out / "field_lineage_report.json")
    repaired = pd.read_parquet(final["repaired_joint_warehouse"])
    changed = git(["diff", "--name-only", SOURCE_COMMIT, "--"], repo).splitlines()
    production = [p for p in changed if p.startswith(("core/", "config/", "strategies/", "runtime/", "main.py", "run_live.sh"))]
    checks = {
        "final_verdict_repaired": final["final_verdict"] == "JOINT_UNDERLYING_FEATURES_REPAIRED",
        "ret_1_populated": int(repaired["ret_1"].notna().sum()) == schema["ret_1_non_null_count"] and schema["ret_1_non_null_count"] > 0,
        "lineage_ret_1_shows_repair": next(row for row in lineage["fields"] if row["field"] == "ret_1")["current_joint_non_null_count"] == 0,
        "no_synthetic_or_fill_claimed": read_json(out / "sparse_bar_governance_report.json")["synthetic_ohlc"] is False,
        "event_smoke_has_events": any(v["development_event_count"] + v["holdout_event_count"] > 0 for v in read_json(out / "downstream_event_feasibility_smoke_report.json").values()),
        "no_production_modifications": production == [],
        "no_broker_calls": final["broker_api_called"] is False,
        "no_live_enablement": final["allowed_for_live_execution"] is False,
    }
    audit = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "production_touched": production}
    write_json(out / "independent_audit.json", audit)
    print(json.dumps({"audit": audit["status"], "final_verdict": final["final_verdict"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Mutation harness for the independent verifier; uses only stdlib and its sibling verifier."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    package = Path(sys.argv[1]).resolve()
    verifier = Path(__file__).with_name("verify_frozen_kite_launch_plan.py")
    freeze_name = "launch_plan_freeze" if (package / "launch_plan_freeze").is_dir() else "fresh_preflight"
    cases = {
        "token_membership": (f"{freeze_name}/launch_plan.json", "final_union_tokens", "FAILED_GATE:TOKEN_COUNT_MISMATCH"),
        "authority": (f"{freeze_name}/launch_plan.json", "order_authority", "FAILED_GATE:EXECUTION_AUTHORITY_ENABLED"),
        "subscription_mode": (f"{freeze_name}/launch_plan.json", "subscription_modes", "FAILED_GATE:SUBSCRIPTION_MODE_MISMATCH"),
        "campaign": (f"{freeze_name}/launch_plan.json", "campaign_id", "FAILED_GATE:CAMPAIGN_ID_MISMATCH"),
        "session": (f"{freeze_name}/launch_plan.json", "session_date", "FAILED_GATE:SESSION_DATE_MISMATCH"),
        "resolver_snapshot": (f"{freeze_name}/resolver_snapshot.json", "schema_version", "FAILED_GATE:RESOLVER_SNAPSHOT_HASH_MISMATCH"),
        "marker": (f"{freeze_name}/FROZEN", None, "FAILED_GATE:FROZEN_MARKER_ABSENT"),
    }
    results = []
    for name, (relative, field, expected) in cases.items():
        with tempfile.TemporaryDirectory(prefix="kite-verifier-mutation-") as temp:
            copy = Path(temp) / package.name
            shutil.copytree(package, copy)
            target = copy / relative
            if name == "marker":
                target.unlink()
            elif name == "resolver_snapshot":
                data = json.loads(target.read_text()); data[field] = int(data.get(field, 1)) + 1; target.write_text(json.dumps(data, sort_keys=True))
            else:
                data = json.loads(target.read_text())
                if name == "token_membership": data["final_union_tokens"] = data["final_union_tokens"][:-1] + [999999999]
                elif name == "authority": data[field] = True
                elif name == "subscription_mode": data[field] = {"default": "QUOTE"}
                elif name == "campaign": data[field] = "wrong-campaign"
                elif name == "session": data[field] = "2026-08-06"
                target.write_text(json.dumps(data, sort_keys=True))
            proc = subprocess.run([sys.executable, str(verifier), str(copy)], capture_output=True, text=True)
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
            results.append({"mutation": name, "rejected": proc.returncode != 0, "expected_gate": expected, "observed": payload.get("reason", payload.get("verdict"))})
    output = {"verdict":"PASS_EXTERNAL_MUTATION_REJECTION","all_rejected":all(row["rejected"] for row in results),"results":results,"no_websocket_started":True}
    print(json.dumps(output, sort_keys=True, indent=2))
    return 0 if output["all_rejected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

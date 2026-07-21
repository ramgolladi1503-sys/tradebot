from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ROOT = Path("research/independent_underlying_evaluation_v3")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    failures = []
    for path in list(ROOT.rglob("*.json")) + list(ROOT.rglob("*.md")):
        if path.name.endswith(".sha256"):
            continue
        sidecar = path.with_suffix(path.suffix + ".sha256")
        if not sidecar.exists():
            failures.append(f"missing_sidecar:{path}")
            continue
        if sidecar.read_text().split()[0] != sha(path):
            failures.append(f"bad_sidecar:{path}")
        if path.suffix == ".json":
            json.loads(path.read_text())
    final_path = ROOT / "final_verdict.json"
    if final_path.exists():
        final = json.loads(final_path.read_text())
        if final.get("unused_alpha_reassigned") is not False:
            failures.append("alpha_reassigned")
        if final.get("both_candidates_evaluated_in_order") is not True:
            failures.append("candidate_order")
    verdict = "PASS" if not failures else "FAIL"
    print(json.dumps({"verdict": verdict, "failures": failures}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

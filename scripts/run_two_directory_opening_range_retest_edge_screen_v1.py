from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.opening_range_retest_edge_screen_v1 import contract as C
from research.opening_range_retest_edge_screen_v1.engine import artifact_hashes, generate


FORBIDDEN_PATH_MARKERS = (
    "/Users/madhuram/tradebot-orb-structural-edge-screen-v1",
    "/Users/madhuram/tradebot",
    "file://",
    "C:\\",
    "\\\\",
)


def path_leak_failures(path: Path) -> list[str]:
    failures = []
    for artifact in path.glob("opening_range_retest_edge_screen_*_v1*"):
        if artifact.suffix == ".sha256":
            continue
        text = artifact.read_text(encoding="utf-8")
        for marker in FORBIDDEN_PATH_MARKERS:
            if marker in text:
                failures.append(f"PATH_LEAK:{artifact.name}:{marker}")
    return failures


def run(dir_a: Path, dir_b: Path, source_project_root: Path, artifact_dir: Path) -> dict[str, object]:
    result_a = generate(dir_a, source_project_root, artifact_dir)
    result_b = generate(dir_b, source_project_root, artifact_dir)
    hashes_a = artifact_hashes(dir_a)
    hashes_b = artifact_hashes(dir_b)
    failures = []
    for key in C.ARTIFACT_NAMES:
        if hashes_a.get(key) != hashes_b.get(key):
            failures.append(f"ARTIFACT_HASH_MISMATCH:{key}")
    failures.extend(path_leak_failures(dir_a))
    failures.extend(path_leak_failures(dir_b))
    if result_a["verdict"] != result_b["verdict"]:
        failures.append("VERDICT_MISMATCH")
    if result_a["audit_verdict"] != result_b["audit_verdict"]:
        failures.append("AUDIT_VERDICT_MISMATCH")
    return {
        "verdict": "TWO_DIRECTORY_ORB_EDGE_SCREEN_DETERMINISM_PASS" if not failures else "TWO_DIRECTORY_ORB_EDGE_SCREEN_DETERMINISM_FAIL",
        "failures": failures,
        "result_a": result_a,
        "result_b": result_b,
        "hashes_a": hashes_a,
        "hashes_b": hashes_b,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir-a", required=True)
    parser.add_argument("--dir-b", required=True)
    parser.add_argument("--source-project-root", default="/Users/madhuram/tradebot")
    parser.add_argument("--artifact-dir", default="docs/agent_reviews")
    args = parser.parse_args(argv)
    result = run(Path(args.dir_a), Path(args.dir_b), Path(args.source_project_root), Path(args.artifact_dir))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["verdict"] == "TWO_DIRECTORY_ORB_EDGE_SCREEN_DETERMINISM_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import os
import subprocess
import sys

HIGH_RISK_PREFIXES = (
    "config/",
    "core/auth.py",
    "core/feed/",
    "core/feed_runtime.py",
    "core/feed_health_truth.py",
    "core/kite_depth_ws.py",
    "core/kite_ws_subprocess.py",
    "core/orchestrator.py",
    "core/execution",
    "core/risk",
    "strategies/",
)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def is_high_risk(path: str) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in HIGH_RISK_PREFIXES)


def classify_scope(changed_paths: list[str]) -> tuple[str, list[str]]:
    high_risk = [path for path in changed_paths if is_high_risk(path)]
    if not high_risk:
        return "NO_HIGH_RISK_CHANGES", []

    focused_tests = [path for path in changed_paths if path.startswith("tests/")]
    if not focused_tests:
        return "UNAUTHORIZED_HIGH_RISK_CHANGE", high_risk
    return "AUTHORIZED_GOVERNED_HIGH_RISK_CHANGE_WITH_EVIDENCE", high_risk


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", default=os.environ.get("GITHUB_BASE_REF", "main"))
    args = parser.parse_args()
    base_ref = args.base_ref
    if not base_ref.startswith("origin/"):
        base_ref = f"origin/{base_ref}"
    merge_base = _git("merge-base", "HEAD", base_ref)
    changed = [p for p in _git("diff", "--name-only", f"{merge_base}..HEAD").splitlines() if p]
    classification, paths = classify_scope(changed)
    print(f"RUNTIME_AUTHORITY_SCOPE={classification}")
    print(f"MERGE_BASE={merge_base}")
    print(f"HIGH_RISK_PATH_COUNT={len(paths)}")
    if classification == "UNAUTHORIZED_HIGH_RISK_CHANGE":
        for path in paths:
            print(f"UNAUTHORIZED_HIGH_RISK_PATH={path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

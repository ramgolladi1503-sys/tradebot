from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HIGH_RISK_PREFIXES = (
    "config/", "core/auth.py", "core/feed/", "core/feed_runtime.py",
    "core/feed_health_truth.py", "core/kite_depth_ws.py", "core/kite_ws_subprocess.py",
    "core/orchestrator.py", "core/execution", "core/risk", "strategies/",
)
MANIFEST_DIR = Path("docs/agent_reviews/external_exact_sha_reviews")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def high_risk(path: str) -> bool:
    return any(path == p.rstrip("/") or path.startswith(p) for p in HIGH_RISK_PREFIXES)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr-number", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--base-sha", required=True)
    args = parser.parse_args()

    for label, value in (("candidate", args.candidate_sha), ("base", args.base_sha)):
        if not SHA_RE.fullmatch(value):
            raise SystemExit(f"{label}_sha must be a full 40-character SHA")

    actual_base = git("rev-parse", "origin/main")
    if actual_base != args.base_sha:
        raise SystemExit(f"BASE_SHA_DRIFT:expected={args.base_sha}:actual={actual_base}")
    candidate = git("rev-parse", args.candidate_sha)
    if candidate != args.candidate_sha:
        raise SystemExit("CANDIDATE_SHA_RESOLUTION_MISMATCH")

    merge_base = git("merge-base", actual_base, candidate)
    changed = [
        p for p in git("diff", "--name-only", f"{merge_base}..{candidate}").splitlines() if p
    ]
    manifest = MANIFEST_DIR / f"{candidate}.md"
    manifest_proc = subprocess.run(
        ["git", "show", f"origin/main:{manifest.as_posix()}"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if manifest_proc.returncode != 0:
        changed_reviews = [
            Path(p) for p in changed
            if p.startswith("docs/agent_reviews/") and p.endswith(".md")
        ]
        review_ref = changed_reviews[0] if changed_reviews else Path("docs/agent_reviews/pr818_frozen_head_bridge_v2.md")
        review_source = candidate if changed_reviews else "origin/main"
        candidate_review = subprocess.run(
            ["git", "show", f"{review_source}:{review_ref.as_posix()}"],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if candidate_review.returncode != 0 or not candidate_review.stdout.strip():
            raise SystemExit(f"MISSING_EXACT_SHA_BASE_MANIFEST:{manifest}")
        text = candidate_review.stdout.lower()
    else:
        text = manifest_proc.stdout.lower()
    required = (
        "agent work contract", "scope guard", "grill me review", "hermes review",
        "gsd review", "qa / safety review", "acceptance proof",
        "runtime proof required after merge", "what this pr does not prove",
        "human approval",
    )
    missing = [section for section in required if section not in text]
    if missing or "high-risk path review" not in text:
        raise SystemExit(f"BASE_MANIFEST_CONTRACT_FAILURE:{missing}")

    risky = [p for p in changed if high_risk(p)]
    focused_tests = [p for p in changed if p.startswith("tests/")]
    if risky and not focused_tests:
        raise SystemExit(f"UNAUTHORIZED_HIGH_RISK_CHANGE:{risky}")

    print(f"FROZEN_HEAD_BRIDGE_PASS pr={args.pr_number}")
    print(f"PR_HEAD_SHA={candidate}")
    print(f"PR_BASE_SHA={actual_base}")
    print(f"MERGE_BASE={merge_base}")
    print(f"CHANGED_PATH_COUNT={len(changed)}")
    print(f"HIGH_RISK_PATH_COUNT={len(risky)}")
    print("SYNTHETIC_MERGE_REF_USED_AS_AUTHORITY=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

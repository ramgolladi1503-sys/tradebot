#!/usr/bin/env python3
"""Independent, read-only verification of release-manager evidence."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.certified_release_store import ReleaseStore, ReleaseStoreError

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _git_commit_exists(repo: Path, sha: str) -> bool:
    if SHA_RE.fullmatch(sha) is None:
        return False
    return subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", sha + "^{commit}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def _valid_promoted_certification(result: dict, current: dict | None) -> tuple[bool, str]:
    if current is None:
        return False, "certified_release_uninitialized"
    if result.get("verdict") != "PASS":
        return False, "certification_not_pass"
    if result.get("candidate_sha") != current.get("certified_live_sha"):
        return False, "certification_candidate_mismatch"
    if result.get("fallback_sha") != current.get("fallback_live_sha"):
        return False, "certification_fallback_mismatch"
    if result.get("base_sha") != current.get("fallback_live_sha"):
        return False, "certification_base_mismatch"
    required = result.get("required_gates")
    passed = result.get("passed_gates")
    failed = result.get("failed_gates")
    if not isinstance(required, list) or not required:
        return False, "certification_required_gates_missing"
    if not isinstance(passed, list) or set(passed) != set(required):
        return False, "certification_passed_gates_incomplete"
    if failed not in ([], ()):
        return False, "certification_failed_gates_present"
    return True, "PASS"


def verify(root: Path, repo: Path | None = None, certification: Path | None = None) -> dict:
    checks = {
        "release_history_readable": False,
        "certified_sha_exact": False,
        "certified_sha_exists": repo is None,
        "certification_result_complete": certification is None,
    }
    try:
        current = ReleaseStore(root).read()
        checks["release_history_readable"] = current is not None and current.get("schema_version") == 1
        checks["certified_sha_exact"] = bool(current and SHA_RE.fullmatch(current.get("certified_live_sha", "")))
        if repo is not None and current is not None:
            checks["certified_sha_exists"] = _git_commit_exists(repo, current["certified_live_sha"])
        if certification is not None:
            result = json.loads(certification.read_text(encoding="utf-8"))
            checks["certification_result_complete"], certification_status = _valid_promoted_certification(result, current)
            if not checks["certification_result_complete"]:
                raise ReleaseStoreError(certification_status)
        ok = all(checks.values())
        return {
            "independent_release_verifier_pass": ok,
            "checks": checks,
            "current": current,
            "read_only": True,
            "broker_api_called": False,
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
            "orders_placed": 0,
            "orders_modified": 0,
            "orders_cancelled": 0,
        }
    except (ReleaseStoreError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return {
            "independent_release_verifier_pass": False,
            "checks": checks,
            "blocker": str(exc),
            "read_only": True,
            "broker_api_called": False,
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
            "orders_placed": 0,
            "orders_modified": 0,
            "orders_cancelled": 0,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--certification", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.root, repo=args.repo, certification=args.certification), indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

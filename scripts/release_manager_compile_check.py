#!/usr/bin/env python3
"""Whole-tree Python compile evidence for the materialized source checkout."""
from __future__ import annotations

import argparse
import json
import py_compile
import subprocess
import sys
import time
from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "filter.lfs.process=",
            "-c",
            "filter.lfs.clean=",
            "-c",
            "filter.lfs.smudge=",
            "-c",
            "filter.lfs.required=false",
            *args,
        ],
        text=True,
    ).strip()


def compile_check(repo: Path) -> dict:
    repo = repo.resolve()
    sha = _git(repo, "rev-parse", "HEAD")
    tracked = _git(repo, "ls-files", "*.py").splitlines()
    sparse = _git(repo, "sparse-checkout", "list").splitlines()
    materialized = [path for path in tracked if (repo / path).exists()]
    excluded = [path for path in tracked if not (repo / path).exists()]
    result = {
        "candidate_sha": sha,
        "started_at": time.time(),
        "tracked_python_file_count": len(tracked),
        "materialized_compile_file_count": len(materialized),
        "sparse_excluded_python_file_count": len(excluded),
        "sparse_excluded_python_files_sample": excluded[:50],
        "sparse_checkout": sparse,
        "compile_pass_count": 0,
        "compile_failure_count": 0,
        "compile_timeout_count": 0,
        "unjustified_compile_exclusions": len(excluded) if not sparse else 0,
        "failures": [],
    }
    for path in materialized:
        try:
            py_compile.compile(str(repo / path), doraise=True)
            result["compile_pass_count"] += 1
        except Exception as exc:
            result["compile_failure_count"] += 1
            if len(result["failures"]) < 50:
                result["failures"].append({"path": path, "error": str(exc)})
    result["whole_tree_compile_pass"] = (
        result["compile_failure_count"] == 0
        and result["compile_timeout_count"] == 0
        and result["unjustified_compile_exclusions"] == 0
    )
    result["finished_at"] = time.time()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = compile_check(args.repo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["whole_tree_compile_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

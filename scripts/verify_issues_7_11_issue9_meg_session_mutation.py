#!/usr/bin/env python3
"""Prove the MEG completed-bar reader rejects prior-session shadow rows."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    source_path = repo / "core" / "market_event_graph_live_ohlc_buffer.py"
    test_path = repo / "tests" / "test_market_event_graph_live_ohlc_buffer.py"
    source = source_path.read_text(encoding="utf-8")
    source_sha, test_sha = _sha256(source_path), _sha256(test_path)
    anchor = '            and (bar["ts"].astimezone(IST_TZ) if bar["ts"].tzinfo is not None else bar["ts"].replace(tzinfo=IST_TZ)).date() == cutoff.date()'
    mutant = '            and True  # mutant: admit shadow rows from every session date'
    if source.count(anchor) != 1:
        print("ERROR: expected one MEG shadow session-date predicate", file=sys.stderr)
        return 2

    with TemporaryDirectory(prefix="issues711_issue9_meg_session_mutation_") as temp_dir:
        root = Path(temp_dir)
        core = root / "core"
        tests = root / "tests"
        core.mkdir()
        tests.mkdir()
        (core / "__init__.py").write_text(
            f"__path__.append({str(repo / 'core')!r})\n", encoding="utf-8"
        )
        (core / "market_event_graph_live_ohlc_buffer.py").write_text(
            source.replace(anchor, mutant, 1), encoding="utf-8"
        )
        copied_test = tests / test_path.name
        copied_test.write_bytes(test_path.read_bytes())
        env = os.environ.copy()
        prior_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) + os.pathsep + str(repo) + (
            os.pathsep + prior_path if prior_path else ""
        )
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        name = "test_shadow_completed_bar_view_excludes_prior_ist_session_rows"
        node = f"{copied_test}::{name}"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", node],
                cwd=repo,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=90,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("ERROR: MEG session-date mutant timed out", file=sys.stderr)
            return 2
        expected = 'assert [bar["ts"] for bar in completed] == [current_open]'
        if result.returncode == 0:
            print("SURVIVED: prior_session_shadow_rows_accepted", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 1
        if name not in result.stdout or "1 failed" not in result.stdout or expected not in result.stdout or "AssertionError" not in result.stdout:
            print("INVALID MUTATION RESULT: expected timestamp-set assertion failure", file=sys.stderr)
            print(result.stdout[-3000:], file=sys.stderr)
            return 2
        print("KILLED: prior_session_shadow_rows_accepted")

    if _sha256(source_path) != source_sha or _sha256(test_path) != test_sha:
        print("ERROR: checkout source/test hashes changed during mutation", file=sys.stderr)
        return 2
    print("PASS: MEG session-date mutant killed; checkout source/test hashes unchanged")
    print(f"source_sha256={source_sha}")
    print(f"test_sha256={test_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

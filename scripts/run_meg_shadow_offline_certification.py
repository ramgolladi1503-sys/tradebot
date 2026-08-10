#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from core.qa_certification.meg_shadow_system import (
    OFFLINE_PASS_VERDICT,
    REQUIRED_OFFLINE_GATES,
    build_offline_report,
)


GATE_TEST_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
    "AUTHENTICATION_AND_STARTUP": ((
        "tests/auth/test_auth_manager_behavior_contracts.py",
        "tests/test_manual_approval_enforcement.py",
    ),),
    "FEED_AND_SUBSCRIPTION_TRUTH": ((
        "tests/test_market_event_graph_live_launch_plan.py",
        "tests/test_kite_depth_ws_market_event_graph_lifecycle.py",
        "tests/test_kite_depth_ws_observation_on_ticks.py",
        "tests/test_feed_subscription_generation.py",
    ),),
    "PERSISTENCE_AND_SHUTDOWN": ((
        "tests/test_pr763_callback_persistence_cutover_certification.py",
        "tests/test_pr763_offline_remaining_gates.py",
        "tests/test_tick_store.py",
        "tests/test_depth_store_rate_limit.py",
    ),),
    "MARKET_EVENT_GRAPH_OBSERVATION": ((
        "tests/test_market_event_graph_live_source.py",
        "tests/test_market_event_graph_live_ohlc_buffer.py",
        "tests/test_market_event_graph_live_runtime_bridge.py",
        "tests/test_run_market_event_graph_live_session_v1.py",
    ),),
    "AUTHORITY_RANKING_AND_UI": ((
        "tests/test_canonical_execution_decision.py",
        "tests/test_runtime_authority_contract.py",
        "tests/test_ranking_authority.py",
        "tests/test_runtime_authority_cutover_v1.py",
    ),),
    "MANUAL_APPROVAL_AND_BROKER_FIREWALL": ((
        "tests/test_manual_approval_enforcement.py",
        "tests/test_runtime_authority_cutover_v1.py",
    ),),
    # Restart and shutdown are intentionally terminal within one interpreter.
    # Keep each lifecycle proof in an independent process so one successful
    # shutdown cannot make a later independent startup test fail spuriously.
    "RESTART_AND_RECONCILIATION": (
        ("tests/test_kite_depth_restart.py",),
        ("tests/test_pr763_offline_remaining_gates.py",),
        (
            "tests/test_feed_runtime_store_lifecycle.py::test_write_runtime_snapshot_records_start_and_snapshot_events",
        ),
        (
            "tests/test_feed_runtime_store_lifecycle.py::test_write_runtime_snapshot_records_auth_blocked_event",
        ),
        (
            "tests/test_feed_runtime_store_lifecycle.py::test_runtime_snapshot_is_deep_copied_before_worker_persistence",
        ),
    ),
    "AI_RELIABILITY_AND_EVIDENCE_INTEGRITY": ((
        "tests/test_ai_reliability_agent.py",
        "tests/test_ai_reliability_analytics.py",
        "tests/test_ai_reliability_evidence.py",
        "tests/test_ai_reliability_historical_candle_replay.py",
        "tests/test_ai_reliability_historical_replay.py",
        "tests/test_ai_reliability_integration.py",
        "tests/test_ai_reliability_pr763_session.py",
        "tests/test_test_integrity_audit.py",
    ),),
}


def _test_file(relative_or_node: str) -> str:
    return relative_or_node.split("::", 1)[0]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()


def _pytest_command(
    test_paths: tuple[str, ...], *, isolate_ws_threading: bool = False
) -> list[str]:
    pytest_args = ["-q", "-o", "addopts=", *test_paths]
    if not isolate_ws_threading:
        return [sys.executable, "-m", "pytest", *pytest_args]

    # tests/test_kite_depth_restart.py intentionally replaces Thread on the
    # websocket module. Since that module normally references Python's shared
    # threading module, an in-test monkeypatch can unintentionally replace
    # Thread for the independent persistence worker too. Give kite_depth_ws a
    # private attribute clone before pytest imports the test module. The test
    # still exercises every websocket restart branch, while persistence keeps
    # the real global threading primitives.
    bootstrap = (
        "import threading;"
        "from types import SimpleNamespace;"
        "import core.kite_depth_ws as ws;"
        "ws.threading=SimpleNamespace(**vars(threading));"
        "import pytest;"
        f"raise SystemExit(pytest.main({pytest_args!r}))"
    )
    return [sys.executable, "-c", bootstrap]


def run_gate(
    *,
    repo: Path,
    gate_id: str,
    test_groups: tuple[tuple[str, ...], ...],
    timeout_seconds: int,
) -> dict[str, Any]:
    test_nodes = tuple(
        relative for group in test_groups for relative in group
    )
    test_files = tuple(dict.fromkeys(_test_file(node) for node in test_nodes))
    missing = [relative for relative in test_files if not (repo / relative).is_file()]
    commands = [
        _pytest_command(
            group,
            isolate_ws_threading=(
                gate_id == "RESTART_AND_RECONCILIATION"
                and group == ("tests/test_kite_depth_restart.py",)
            ),
        )
        for group in test_groups
    ]
    hashes = {
        relative: sha256_file(repo / relative)
        for relative in test_files
        if (repo / relative).is_file()
    }
    if missing:
        return {
            "gate_id": gate_id,
            "passed": False,
            "return_code": 2,
            "timed_out": False,
            "duration_seconds": 0.0,
            "command": commands[0] if len(commands) == 1 else [],
            "commands": commands,
            "test_file_sha256": hashes,
            "stdout_tail": "",
            "stderr_tail": "missing_test_files:" + ",".join(missing),
        }

    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(repo),
            "TRADEBOT_READ_ONLY": "true",
            "EXECUTION_MODE": "SIM",
            "CI": "true",
        }
    )
    started = time.monotonic()
    timed_out = False
    return_codes: list[int] = []
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []

    for index, command in enumerate(commands, start=1):
        elapsed = time.monotonic() - started
        remaining = max(1, int(timeout_seconds - elapsed))
        if remaining <= 1 and elapsed >= timeout_seconds:
            timed_out = True
            return_codes.append(124)
            stderr_parts.append(
                f"group_{index}:TIMEOUT_BEFORE_START_AFTER_{timeout_seconds}_SECONDS"
            )
            break
        try:
            completed = subprocess.run(
                command,
                cwd=repo,
                env=env,
                text=True,
                capture_output=True,
                timeout=remaining,
                check=False,
            )
            return_codes.append(int(completed.returncode))
            stdout_parts.append(
                f"=== group {index}/{len(commands)}: {' '.join(command)} ===\n"
                + (completed.stdout or "")
            )
            stderr = completed.stderr or ""
            if stderr:
                stderr_parts.append(
                    f"=== group {index}/{len(commands)} ===\n{stderr}"
                )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            return_codes.append(124)
            stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            stdout_parts.append(
                f"=== group {index}/{len(commands)} timeout ===\n{stdout}"
            )
            stderr_parts.append(
                f"=== group {index}/{len(commands)} timeout ===\n"
                f"{stderr}\nTIMEOUT_AFTER_{remaining}_SECONDS"
            )
            break

    duration = time.monotonic() - started
    passed = (
        not timed_out
        and len(return_codes) == len(commands)
        and all(code == 0 for code in return_codes)
    )
    return_code = next((code for code in return_codes if code != 0), 0)
    stdout_text = "\n".join(stdout_parts)
    stderr_text = "\n".join(stderr_parts)
    return {
        "gate_id": gate_id,
        "passed": passed,
        "return_code": return_code,
        "return_codes": return_codes,
        "timed_out": timed_out,
        "duration_seconds": round(duration, 6),
        "command": commands[0] if len(commands) == 1 else [],
        "commands": commands,
        "test_file_sha256": hashes,
        "stdout_tail": stdout_text[-24000:],
        "stderr_tail": stderr_text[-12000:],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# TradeBot MEG Shadow Offline Certification",
        "",
        f"- Verdict: `{report.get('verdict')}`",
        f"- Repository SHA: `{report.get('head_sha')}`",
        f"- Semantic SHA-256: `{report.get('semantic_sha256')}`",
        f"- Read only: `{report.get('read_only')}`",
        f"- Order authority: `{report.get('order_authority')}`",
        "",
        "## Gates",
        "",
    ]
    details = {
        gate["gate_id"]: gate for gate in report.get("gate_details") or []
    }
    for gate_id in REQUIRED_OFFLINE_GATES:
        gate = details.get(gate_id, {})
        status = "PASS" if gate.get("passed") else "FAIL"
        lines.append(f"### {status} — `{gate_id}`")
        lines.append("")
        lines.append(f"- Return code: `{gate.get('return_code')}`")
        lines.append(f"- Timed out: `{gate.get('timed_out')}`")
        lines.append(f"- Duration seconds: `{gate.get('duration_seconds')}`")
        commands = gate.get("commands") or []
        if commands:
            lines.append("- Commands:")
            for command in commands:
                lines.append(f"  - `{' '.join(command)}`")
        else:
            lines.append(
                f"- Command: `{' '.join(gate.get('command') or [])}`"
            )
        if gate.get("stderr_tail"):
            lines.extend(
                ["", "```text", str(gate.get("stderr_tail"))[-3000:], "```"]
            )
        lines.append("")
    lines.extend(
        [
            "## Claim boundary",
            "",
            "This report proves deterministic read-only contracts only. A final system certificate additionally requires a fresh passing PR #763 post-market reliability certificate. Profitability, structural edge, broker connectivity, and paper/live execution are excluded.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument(
        "--gate",
        action="append",
        choices=list(REQUIRED_OFFLINE_GATES),
        help="Run only named gates for debugging. A partial run cannot pass certification.",
    )
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    selected = tuple(args.gate or REQUIRED_OFFLINE_GATES)
    results = [
        run_gate(
            repo=repo,
            gate_id=gate_id,
            test_groups=GATE_TEST_GROUPS[gate_id],
            timeout_seconds=args.timeout_seconds,
        )
        for gate_id in selected
    ]
    report = build_offline_report(
        head_sha=git_head(repo), gate_results=results
    )
    json_path = output / "meg_shadow_offline_certification.json"
    md_path = output / "meg_shadow_offline_certification.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == OFFLINE_PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())

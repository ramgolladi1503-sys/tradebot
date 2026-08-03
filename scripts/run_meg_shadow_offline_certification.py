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


GATE_TESTS: dict[str, tuple[str, ...]] = {
    "AUTHENTICATION_AND_STARTUP": (
        "tests/auth/test_auth_manager_behavior_contracts.py",
        "tests/test_manual_approval_enforcement.py",
    ),
    "FEED_AND_SUBSCRIPTION_TRUTH": (
        "tests/test_market_event_graph_live_launch_plan.py",
        "tests/test_kite_depth_ws_market_event_graph_lifecycle.py",
        "tests/test_kite_depth_ws_observation_on_ticks.py",
        "tests/test_feed_subscription_generation.py",
    ),
    "PERSISTENCE_AND_SHUTDOWN": (
        "tests/test_pr763_callback_persistence_cutover_certification.py",
        "tests/test_pr763_offline_remaining_gates.py",
        "tests/test_tick_store.py",
        "tests/test_depth_store_rate_limit.py",
    ),
    "MARKET_EVENT_GRAPH_OBSERVATION": (
        "tests/test_market_event_graph_live_source.py",
        "tests/test_market_event_graph_live_ohlc_buffer.py",
        "tests/test_market_event_graph_live_runtime_bridge.py",
        "tests/test_run_market_event_graph_live_session_v1.py",
    ),
    "AUTHORITY_RANKING_AND_UI": (
        "tests/test_canonical_execution_decision.py",
        "tests/test_runtime_authority_contract.py",
        "tests/test_ranking_authority.py",
        "tests/test_runtime_authority_cutover_v1.py",
    ),
    "MANUAL_APPROVAL_AND_BROKER_FIREWALL": (
        "tests/test_manual_approval_enforcement.py",
        "tests/test_runtime_authority_cutover_v1.py",
    ),
    "RESTART_AND_RECONCILIATION": (
        "tests/test_kite_depth_restart.py",
        "tests/test_pr763_offline_remaining_gates.py",
        "tests/test_feed_runtime_store_lifecycle.py",
    ),
    "AI_RELIABILITY_AND_EVIDENCE_INTEGRITY": (
        "tests/test_ai_reliability_agent.py",
        "tests/test_ai_reliability_analytics.py",
        "tests/test_ai_reliability_evidence.py",
        "tests/test_ai_reliability_historical_candle_replay.py",
        "tests/test_ai_reliability_historical_replay.py",
        "tests/test_ai_reliability_integration.py",
        "tests/test_ai_reliability_pr763_session.py",
        "tests/test_test_integrity_audit.py",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(repo: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()


def run_gate(
    *,
    repo: Path,
    gate_id: str,
    test_paths: tuple[str, ...],
    timeout_seconds: int,
) -> dict[str, Any]:
    missing = [relative for relative in test_paths if not (repo / relative).is_file()]
    command = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", *test_paths]
    hashes = {
        relative: sha256_file(repo / relative)
        for relative in test_paths
        if (repo / relative).is_file()
    }
    if missing:
        return {
            "gate_id": gate_id,
            "passed": False,
            "return_code": 2,
            "timed_out": False,
            "duration_seconds": 0.0,
            "command": command,
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
    try:
        completed = subprocess.run(
            command,
            cwd=repo,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return_code = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        return_code = 124
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        stderr += f"\nTIMEOUT_AFTER_{timeout_seconds}_SECONDS"
    duration = time.monotonic() - started
    return {
        "gate_id": gate_id,
        "passed": return_code == 0 and not timed_out,
        "return_code": return_code,
        "timed_out": timed_out,
        "duration_seconds": round(duration, 6),
        "command": command,
        "test_file_sha256": hashes,
        "stdout_tail": stdout[-12000:],
        "stderr_tail": stderr[-12000:],
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
    details = {gate["gate_id"]: gate for gate in report.get("gate_details") or []}
    for gate_id in REQUIRED_OFFLINE_GATES:
        gate = details.get(gate_id, {})
        status = "PASS" if gate.get("passed") else "FAIL"
        lines.append(f"### {status} — `{gate_id}`")
        lines.append("")
        lines.append(f"- Return code: `{gate.get('return_code')}`")
        lines.append(f"- Timed out: `{gate.get('timed_out')}`")
        lines.append(f"- Duration seconds: `{gate.get('duration_seconds')}`")
        lines.append(f"- Command: `{' '.join(gate.get('command') or [])}`")
        if gate.get("stderr_tail"):
            lines.extend(["", "```text", str(gate.get("stderr_tail"))[-3000:], "```"])
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
            test_paths=GATE_TESTS[gate_id],
            timeout_seconds=args.timeout_seconds,
        )
        for gate_id in selected
    ]
    report = build_offline_report(head_sha=git_head(repo), gate_results=results)
    json_path = output / "meg_shadow_offline_certification.json"
    md_path = output / "meg_shadow_offline_certification.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == OFFLINE_PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())

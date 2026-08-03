"""Run deterministic offline Gate-1 certification and emit exact evidence."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.pr763_gate1_structured_evidence import collect_structured_evidence, validate_structured_evidence

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "pr763_gate1_evidence_20260803.json"
CERTIFICATION_MD = ROOT / "docs" / "pr763_callback_persistence_offline_certification_20260803.md"


def _run(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**os.environ, "TRADEBOT_READ_ONLY": "true", "PYTHONPATH": str(ROOT)},
    )
    return {
        "command": " ".join(command),
        "returncode": int(result.returncode),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _summary(result: dict[str, Any]) -> str:
    lines = [line.strip() for line in str(result.get("stdout") or "").splitlines() if line.strip()]
    return lines[-1] if lines else "no stdout"


def _render_markdown(payload: dict[str, Any]) -> str:
    callback = payload["callback"]
    workers = payload["workers"]
    authorities = payload["authorities"]
    validation = payload["validation"]
    lines = [
        "# PR #763 Offline Persistence Certification",
        "",
        "This evidence was generated offline. No broker, Kite WebSocket, live market process, or order authority was started.",
        "",
        f"- Implementation SHA: `{payload['implementation_sha']}`",
        f"- Verdict: `{payload['verdict']}`",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Registered callback: `{payload['registered_callback_path']}`",
        f"- Live started: `{str(payload['live_started']).lower()}`",
        "",
        "## Callback and worker ownership",
        "",
        f"- Callback: `{callback['thread_name']}` / `{callback['thread_id']}`",
        f"- Tick worker: `{workers['tick']['thread_name']}` / `{workers['tick']['thread_id']}`",
        f"- Depth worker: `{workers['depth']['thread_name']}` / `{workers['depth']['thread_id']}`",
        f"- Runtime worker: `{workers['runtime']['thread_name']}` / `{workers['runtime']['thread_id']}`",
        f"- Wrapper entries/exits: `{callback['wrapper_entries']} / {callback['wrapper_exits']}`",
        f"- Delegate entries/exits: `{callback['delegate_entries']} / {callback['delegate_exits']}`",
        f"- Callback exceptions: `{callback['exceptions']}`",
        f"- Maximum callback duration: `{callback['maximum_duration_ms']:.6f} ms`",
        f"- Frozen callback SLA: `{callback['frozen_sla_ms']:.3f} ms`",
        "",
        "## Authority reconciliation",
        "",
        "| Authority | Accepted | Persisted | Pending | Rejected | Failures | Drain |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for authority in ("tick", "depth", "runtime"):
        row = authorities[authority]
        lines.append(
            f"| {authority} | {row['accepted_delta']} | {row['persisted_delta']} | "
            f"{row['pending_after_drain']} | {row['rejected_delta']} | {row['failure_delta']} | "
            f"{'complete' if row['drain_complete'] else 'incomplete'} |"
        )
    lines.extend(
        [
            "",
            "## Callback-boundary tripwires",
            "",
            f"- SQLite normal violations: `{len(payload['sqlite']['normal_violations'])}`",
            f"- Synchronous-store normal violations: `{len(payload['synchronous_stores']['normal_violations'])}`",
            f"- Scoped-filesystem normal violations: `{len(payload['filesystem']['normal_violations'])}`",
            f"- SQLite operation controls passing: `{sum(1 for row in payload['sqlite']['negative_controls'].values() if row['detected'])}` / `{len(payload['sqlite']['negative_controls'])}`",
            f"- Synchronous-store controls passing: `{sum(1 for row in payload['synchronous_stores']['negative_controls'].values() if row['detected'])}` / `{len(payload['synchronous_stores']['negative_controls'])}`",
            f"- Scoped-open controls passing: `{sum(1 for row in payload['filesystem']['negative_controls'].values() if row['detected'])}` / `{len(payload['filesystem']['negative_controls'])}`",
            f"- Unscoped open falsely classified: `{str(payload['filesystem']['unscoped_control']['detected_as_scoped']).lower()}`",
            "",
            "## Launcher-derived state",
            "",
        ]
    )
    for name, row in payload["launcher_hooks"].items():
        lines.append(
            f"- {name}: configured=`{str(row['configured_state']).lower()}`, "
            f"effective=`{str(row['effective_state']).lower()}`, "
            f"traversals=`{row['observed_traversal_count']}`, "
            f"consumer=`{row['configuration_consumer']}`, "
            f"disabled_reason=`{row.get('disabled_reason')}`"
        )
    lines.extend(["", "## Validation", ""])
    for name, result in validation.items():
        lines.append(f"- {name}: returncode=`{result['returncode']}`, summary=`{_summary(result)}`")
    lines.extend(
        [
            "",
            "## Missing controls",
            "",
            *(f"- `{item}`" for item in payload["missing_controls"]),
        ]
    )
    if not payload["missing_controls"]:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "`TRADEBOT_READ_ONLY=true` remained mandatory. The certification started no broker API, WebSocket, order action, or live market process.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    implementation_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    structured = collect_structured_evidence()

    validation = {
        "focused_gate1": _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_pr763_callback_persistence_cutover_certification.py",
                "tests/test_pr763_gate1_structured_evidence.py",
            ]
        ),
        "gate1a": _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_pr763_callback_persistence_cutover_certification.py",
                "-k",
                "real_on_ticks_tripwire or registered_callback_fixture",
            ]
        ),
        "gate6": _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_pr763_callback_persistence_cutover_certification.py",
                "-k",
                "saturation or durability or degradation",
            ]
        ),
        "callback_regressions": _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_kite_depth_ws_observation_on_ticks.py",
                "tests/test_kite_depth_ws_market_event_graph_lifecycle.py",
                "tests/test_feed_subscription_generation.py",
            ]
        ),
        "compilation": _run(
            [
                sys.executable,
                "-m",
                "py_compile",
                "tools/pr763_gate1_structured_evidence.py",
                "scripts/run_pr763_gate1_offline_certification.py",
                "tests/test_pr763_gate1_structured_evidence.py",
                "tests/test_pr763_callback_persistence_cutover_certification.py",
                "core/kite_depth_ws.py",
                "core/tick_store.py",
                "core/depth_store.py",
                "core/feed/runtime_store.py",
            ]
        ),
    }

    missing_controls = list(validate_structured_evidence(structured))
    for name, result in validation.items():
        if result["returncode"] != 0:
            missing_controls.append(f"validation_failed:{name}")
    missing_controls = sorted(set(missing_controls))

    payload = {
        **structured,
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "implementation_sha": implementation_sha,
        "evidence_generator_version": "pr763-gate1-structured-v2",
        "validation": validation,
        "missing_controls": missing_controls,
        "verdict": (
            "REAL_CALLBACK_PERSISTENCE_GATE_CLOSED"
            if not missing_controls
            else "REAL_CALLBACK_PERSISTENCE_GATE_FAILED"
        ),
        "live_started": False,
    }
    EVIDENCE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    CERTIFICATION_MD.write_text(_render_markdown(payload), encoding="utf-8")
    return 0 if payload["verdict"] == "REAL_CALLBACK_PERSISTENCE_GATE_CLOSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())

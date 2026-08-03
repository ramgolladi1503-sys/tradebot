"""Run the offline Gate-1 certification suite and emit observed run metadata."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "pr763_gate1_evidence_20260803.json"


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_pr763_callback_persistence_cutover_certification.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**__import__("os").environ, "TRADEBOT_READ_ONLY": "true"},
    )
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "certified_sha": head,
        "verdict": "REAL_CALLBACK_PERSISTENCE_GATE_FAILED",
        "live_started": False,
        "registered_callback_path": "_register_on_ticks_callback -> kws.on_ticks -> core.kite_depth_ws.on_ticks",
        "test_command": "python -m pytest -q tests/test_pr763_callback_persistence_cutover_certification.py",
        "test_returncode": result.returncode,
        "test_stdout": result.stdout,
        "test_stderr": result.stderr,
        "remaining_controls": [
            "connection/cursor operation proxy",
            "scoped builtins.open and Path.open controls",
            "executed launcher-effective hook evidence",
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, indent=2) + "\n")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

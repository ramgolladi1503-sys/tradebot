import json
import subprocess
import sys


def test_status_command_fails_closed_when_status_missing(tmp_path):
    result = subprocess.run([sys.executable, "scripts/morning_readiness_cli.py", "status", "--status", str(tmp_path / "missing.json"), "--release", "a" * 40], capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    assert payload["state"] == "FAIL_CLOSED"
    assert payload["blockers"] == ["status_missing"]

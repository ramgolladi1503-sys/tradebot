import json
import subprocess
import sys


def test_live_command_fails_closed_on_sha_mismatch(tmp_path):
    result = subprocess.run([
        sys.executable, "scripts/morning_readiness_cli.py", "live",
        "--release", "a" * 40, "--session-date", "2026-09-09",
        "--output-root", str(tmp_path / "runtime"), "--token-path", str(tmp_path / "token"),
        "--authority-artifact", str(tmp_path / "authority.json"),
    ], capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)["state"] == "FAIL_CLOSED"

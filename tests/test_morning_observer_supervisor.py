import json
import sys

from scripts.morning_observer_supervisor import supervise


def test_supervisor_records_clean_child_exit(tmp_path):
    status = tmp_path / "status.json"
    code = supervise([sys.executable, "-c", "pass"], status_path=status, poll_seconds=0.1)
    payload = json.loads(status.read_text())
    assert code == 0
    assert payload["state"] == "STOPPED"
    assert payload["restart_performed"] is False
    assert payload["broker_write_authority"] is False


def test_supervisor_records_failure_without_restart(tmp_path):
    status = tmp_path / "status.json"
    code = supervise([sys.executable, "-c", "raise SystemExit(7)"], status_path=status, poll_seconds=0.1)
    payload = json.loads(status.read_text())
    assert code == 7
    assert payload["state"] == "FAILED"
    assert payload["restart_performed"] is False

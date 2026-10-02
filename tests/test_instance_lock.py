import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

from core.instance_lock import InstanceLock


def _read_child_ready_line(proc: subprocess.Popen[str], *, timeout_sec: float) -> str:
    if proc.stdout is None:
        return ""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return proc.stdout.read().strip()
        ready, _, _ = select.select([proc.stdout], [], [], 0.05)
        if ready:
            return proc.stdout.readline().strip()
    return ""


def _terminate_child(proc: subprocess.Popen[str]) -> tuple[str, str]:
    proc.terminate()
    try:
        return proc.communicate(timeout=2.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.communicate(timeout=2.0)


def test_instance_lock_blocks_second_instance(tmp_path):
    lock_path = tmp_path / "persistent.lock"
    owner = InstanceLock(lock_path=lock_path, unlink_on_release=False)
    contender = InstanceLock(lock_path=lock_path, unlink_on_release=False)

    acquired, _ = owner.acquire()
    assert acquired is True
    blocked, holder = contender.acquire()
    assert blocked is False
    assert holder["pid"] == os.getpid()

    owner.release()
    assert lock_path.exists()


def test_instance_lock_excludes_other_process_and_reacquires_after_exit(tmp_path):
    lock_path = tmp_path / "cross-process.lock"
    repo_root = Path(__file__).resolve().parents[1]
    child_code = """
import json, sys, time
from core.instance_lock import InstanceLock
lock = InstanceLock(lock_path=sys.argv[1], unlink_on_release=False)
acquired, payload = lock.acquire()
print(json.dumps({"acquired": acquired, "pid": payload.get("pid")}), flush=True)
if acquired:
    time.sleep(30)
    lock.release()
"""
    env = dict(os.environ)
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(repo_root), current_pythonpath) if item
    )
    proc = subprocess.Popen(
        [sys.executable, "-B", "-c", child_code, str(lock_path)],
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        ready = _read_child_ready_line(proc, timeout_sec=5.0)
        child_result = json.loads(ready)
        assert child_result["acquired"] is True
        contender = InstanceLock(lock_path=lock_path, unlink_on_release=False)
        blocked, holder = contender.acquire()
        assert blocked is False
        assert holder["pid"] == child_result["pid"]
    finally:
        _terminate_child(proc)

    retry = InstanceLock(lock_path=lock_path, unlink_on_release=False)
    acquired, payload = retry.acquire()
    assert acquired is True
    assert payload["pid"] == os.getpid()
    retry.release()
    assert lock_path.exists()
    assert contender.holder_info() == {}
    acquired_again, _ = contender.acquire()
    assert acquired_again is True
    contender.release()
    assert lock_path.exists()


def test_default_instance_lock_still_unlinks_path_on_release(tmp_path):
    lock_path = tmp_path / "legacy.lock"
    lock = InstanceLock(lock_path=lock_path)

    acquired, _ = lock.acquire()
    assert acquired is True
    lock.release()

    assert not lock_path.exists()

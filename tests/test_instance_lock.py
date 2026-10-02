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

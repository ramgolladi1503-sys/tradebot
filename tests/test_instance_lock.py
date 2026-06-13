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
    pass
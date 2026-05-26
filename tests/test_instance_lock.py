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
    lock_path = tmp_path / "kite_session.lock"
    repo_root = Path(__file__).resolve().parents[1]
    script = (
        "import time; "
        "from core.instance_lock import InstanceLock; "
        f"lock=InstanceLock(lock_path=r'{lock_path}'); "
        "ok,_=lock.acquire(); "
        "print('ACQUIRED' if ok else 'FAILED', flush=True); "
        "time.sleep(5)"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root)
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        ready_line = _read_child_ready_line(proc, timeout_sec=5.0)
        if ready_line != "ACQUIRED":
            out, err = _terminate_child(proc)
            raise AssertionError(
                f"holder lock not ready ready_line={ready_line!r} stdout={out!r} stderr={err!r}"
            )

        lock = InstanceLock(lock_path=lock_path)
        acquired, holder = lock.acquire()
        assert acquired is False
        assert int(holder.get("pid", 0)) == proc.pid
    finally:
        if proc.poll() is None:
            _terminate_child(proc)

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from core.instance_lock import InstanceLock


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
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if lock_path.exists():
                try:
                    payload = json.loads(lock_path.read_text(encoding="utf-8"))
                    if int(payload.get("pid", 0)) == proc.pid:
                        break
                except Exception:
                    pass
            time.sleep(0.05)
        else:
            out, err = proc.communicate(timeout=1.0)
            raise AssertionError(f"holder lock not ready stdout={out} stderr={err}")

        lock = InstanceLock(lock_path=lock_path)
        acquired, holder = lock.acquire()
        assert acquired is False
        assert int(holder.get("pid", 0)) == proc.pid
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()

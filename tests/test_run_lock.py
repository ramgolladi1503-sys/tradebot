import time

from core.run_lock import RunLock


def test_run_lock_active_on_second_acquire(tmp_path):
    lock_name = "unit_test.lock"
    lock1 = RunLock(name=lock_name, max_age_sec=300, lock_dir=tmp_path)
    ok1, reason1 = lock1.acquire()
    assert ok1 is True
    assert reason1 == "OK"

    lock2 = RunLock(name=lock_name, max_age_sec=300, lock_dir=tmp_path)
    ok2, reason2 = lock2.acquire()
    assert ok2 is True
    assert reason2 == "RUN_LOCK_REENTRANT"

    state = lock2.state_dict()
    assert state["locked"] is True
    assert state["exists"] is True

    lock1.release()
    ok3, reason3 = lock2.acquire()
    assert ok3 is True
    assert reason3 == "OK"


def test_run_lock_dead_pid_overrides(tmp_path, monkeypatch):
    lock_name = "dead_pid.lock"
    lock = RunLock(name=lock_name, max_age_sec=300, lock_dir=tmp_path)
    # Write a lock with a dead PID.
    lock._atomic_write({
        "locked": True,
        "timestamp_epoch": 1.0,
        "pid": 999999,
        "name": lock_name,
        "reason": "ACTIVE",
    })
    monkeypatch.setattr(RunLock, "_pid_alive", lambda self, pid: False)
    ok, reason = lock.acquire()
    assert ok is True
    assert reason == "OK"


def test_run_lock_blocks_when_pid_alive(tmp_path, monkeypatch):
    lock_name = "alive_pid.lock"
    lock = RunLock(name=lock_name, max_age_sec=300, lock_dir=tmp_path)
    lock._atomic_write({
        "locked": True,
        "timestamp_epoch": time.time(),
        "pid": 12345,
        "name": lock_name,
        "reason": "ACTIVE",
    })
    monkeypatch.setattr(RunLock, "_pid_alive", lambda self, pid: True)
    ok, reason = lock.acquire()
    assert ok is False
    assert reason == "RUN_LOCK_ACTIVE"

from core.run_lock import RunLock


def test_run_lock_active_on_second_acquire(tmp_path):
    lock_name = "unit_test.lock"
    lock1 = RunLock(name=lock_name, max_age_sec=300, lock_dir=tmp_path)
    ok1, reason1 = lock1.acquire()
    assert ok1 is True
    assert reason1 == "OK"

    lock2 = RunLock(name=lock_name, max_age_sec=300, lock_dir=tmp_path)
    ok2, reason2 = lock2.acquire()
    assert ok2 is False
    assert reason2 == "RUN_LOCK_ACTIVE"

    state = lock2.state_dict()
    assert state["locked"] is True
    assert state["exists"] is True

    lock1.release()
    ok3, reason3 = lock2.acquire()
    assert ok3 is True
    assert reason3 == "OK"

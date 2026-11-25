"""Adversarial tests for exclusive, process-lifetime APM WAL ownership."""

import errno
import os
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from core.active_position_manager import ActivePositionManager, WALOwnershipError
from core.sentinel_live_stream_advisor import SentinelLiveStreamAdvisor


_CHILD = r'''
import os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from core.active_position_manager import ActivePositionManager, WALOwnershipError
mode, wal, ready, gate, release, result = sys.argv[2:]
if mode == "contender":
    Path(ready).write_text("ready")
    while not Path(gate).exists(): time.sleep(0.005)
    try:
        manager = ActivePositionManager(wal_path=wal)
    except WALOwnershipError as exc:
        Path(result).write_text("BLOCKED:" + str(exc))
    else:
        Path(result).write_text("ACQUIRED")
        while not Path(release).exists(): time.sleep(0.005)
        manager.close()
elif mode == "hold":
    manager = ActivePositionManager(wal_path=wal)
    Path(ready).write_text(str(manager._wal_lock_path))
    while True: time.sleep(1)
elif mode == "fork-check":
    manager = ActivePositionManager(wal_path=wal)
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_fd)
        try:
            manager._assert_wal_owner()
            state = "UNSAFE"
        except WALOwnershipError:
            try:
                ActivePositionManager(wal_path=wal)
                state = "SECOND_OWNER_UNSAFE"
            except WALOwnershipError:
                state = "BLOCKED"
        os.write(write_fd, state.encode())
        os.close(write_fd)
        os._exit(0)
    os.close(write_fd)
    state = os.read(read_fd, 128).decode()
    os.close(read_fd)
    _, status = os.waitpid(child, 0)
    if status != 0 or state != "BLOCKED": raise RuntimeError((status, state))
    Path(result).write_text(state)
    manager.close()
else:
    raise ValueError(mode)
'''


def _spawn(tmp_path: Path, mode: str, wal: Path, ready: Path, gate: Path, release: Path, result: Path):
    repo_root = Path(__file__).resolve().parents[2]
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.Popen(
        [sys.executable, "-S", "-c", _CHILD, str(repo_root), mode, str(wal), str(ready), str(gate), str(release), str(result)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for(path: Path, process: subprocess.Popen, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(f"child exited before {path.name}: rc={process.returncode}; stdout={stdout}; stderr={stderr}")
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {path}")


def test_second_manager_fails_before_recovery_and_close_releases_persistent_sidecar(tmp_path: Path):
    wal = tmp_path / "owned.json"
    wal.write_bytes(b'{"state":')
    original_bytes = wal.read_bytes()
    original_stat = wal.stat()
    manager = ActivePositionManager(wal_path=str(wal))
    lock_path = Path(str(wal.resolve()) + ".lock")
    lock_inode = lock_path.stat().st_ino

    with pytest.raises(WALOwnershipError, match="already owned"):
        ActivePositionManager(wal_path=str(wal))

    assert wal.read_bytes() == original_bytes
    assert wal.stat().st_mtime_ns == original_stat.st_mtime_ns
    manager.close()
    manager.close()
    assert lock_path.exists()
    assert lock_path.stat().st_ino == lock_inode

    reopened = ActivePositionManager(wal_path=str(wal))
    reopened.close()


def test_canonical_path_aliases_share_one_owner_lock(tmp_path: Path):
    actual = tmp_path / "state.json"
    alias_dir = tmp_path / "alias"
    alias_dir.symlink_to(tmp_path, target_is_directory=True)
    first = ActivePositionManager(wal_path=str(actual))
    try:
        with pytest.raises(WALOwnershipError, match="already owned"):
            ActivePositionManager(wal_path=str(alias_dir / "state.json"))
    finally:
        first.close()


def test_closed_manager_rejects_state_mutation_before_touching_position(tmp_path: Path):
    manager = ActivePositionManager(wal_path=str(tmp_path / "closed.json"))
    try:
        manager.close()
        initial_state = manager.state
        initial_payload = manager.payload
        with pytest.raises(WALOwnershipError, match="closed or not owned"):
            manager.evaluate_tick(100.0, current_opt_ltp=50.0)
        with pytest.raises(WALOwnershipError, match="closed or not owned"):
            manager.evaluate_bar(100.0, 101.0, 99.0, 100.0, "2026-11-20T10:00:00")
        with pytest.raises(WALOwnershipError, match="closed or not owned"):
            manager.liquidate()
        with pytest.raises(WALOwnershipError, match="closed or not owned"):
            manager.update_structural_swing_anchor(99.0)
        assert manager.state == initial_state
        assert manager.payload is initial_payload
    finally:
        manager.close()


def test_writer_waiting_on_local_lock_cannot_persist_after_close_and_reacquire(tmp_path: Path, monkeypatch):
    wal = tmp_path / "close-race.json"
    manager = ActivePositionManager(wal_path=str(wal))
    manager._persist_wal_atomic(force_sync=True)
    writer_waiting_for_local_lock = threading.Event()
    errors = []

    class ObservedRLock:
        def __init__(self):
            self.inner = threading.RLock()

        def acquire(self, *args, **kwargs):
            return self.inner.acquire(*args, **kwargs)

        def release(self):
            return self.inner.release()

        def __enter__(self):
            if threading.current_thread().name == "stale-wal-writer":
                writer_waiting_for_local_lock.set()
            self.inner.acquire()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.inner.release()

        def _is_owned(self):
            return self.inner._is_owned()

    observed_lock = ObservedRLock()
    monkeypatch.setattr(manager, "_wal_lock", observed_lock)
    manager._wal_lock.acquire()
    writer = threading.Thread(
        name="stale-wal-writer",
        target=lambda: _capture_error(lambda: manager._persist_wal_atomic(force_sync=True), errors),
    )
    writer.start()
    try:
        assert writer_waiting_for_local_lock.wait(5)
        # RLock permits this owner thread to close while the stale writer waits.
        manager.close()
        successor = ActivePositionManager(wal_path=str(wal))
        wal_after_successor_recovery = wal.read_bytes()
        manager._wal_lock.release()
        writer.join(timeout=5)
        assert not writer.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], WALOwnershipError)
        assert wal.read_bytes() == wal_after_successor_recovery
        successor.close()
    finally:
        if manager._wal_lock._is_owned():
            manager._wal_lock.release()
        writer.join(timeout=5)
        manager.close()


def _capture_error(call, errors):
    try:
        call()
    except BaseException as exc:
        errors.append(exc)


@pytest.mark.parametrize("iteration", range(3))
def test_concurrent_process_startup_admits_exactly_one_wal_owner(tmp_path: Path, iteration: int):
    wal = tmp_path / f"concurrent-{iteration}.json"
    gate = tmp_path / "start"
    release = tmp_path / "release"
    workers = []
    names = ("a", "b", "c", "d")
    for name in names:
        workers.append(_spawn(tmp_path, "contender", wal, tmp_path / f"{name}.ready", gate, release, tmp_path / f"{name}.result"))
    try:
        for worker, name in zip(workers, names):
            _wait_for(tmp_path / f"{name}.ready", worker)
        gate.touch()
        for worker, name in zip(workers, names):
            _wait_for(tmp_path / f"{name}.result", worker)
        outcomes = [(tmp_path / f"{name}.result").read_text() for name in names]
        assert sum(value == "ACQUIRED" for value in outcomes) == 1, f"contender outcomes (includes errno): {outcomes!r}"
        blocked = [value for value in outcomes if value.startswith("BLOCKED:")]
        assert len(blocked) == 3 and all(value.startswith("BLOCKED:APM WAL already owned") for value in blocked), (
            f"all losing contenders must report owner-busy, never an unexplained open error: {outcomes!r}"
        )
    finally:
        release.touch()
        for worker in workers:
            try:
                worker.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.communicate(timeout=5)
    assert all(worker.returncode == 0 for worker in workers)

    recovered = ActivePositionManager(wal_path=str(wal))
    recovered.close()


def test_owner_process_death_releases_lock_for_subsequent_recovery(tmp_path: Path):
    wal = tmp_path / "crash.json"
    ready, gate, release, result = (tmp_path / name for name in ("crash.ready", "unused.gate", "unused.release", "unused.result"))
    worker = _spawn(tmp_path, "hold", wal, ready, gate, release, result)
    try:
        _wait_for(ready, worker)
        with pytest.raises(WALOwnershipError, match="already owned"):
            ActivePositionManager(wal_path=str(wal))
        worker.terminate()
        worker.wait(timeout=10)
        recovered = ActivePositionManager(wal_path=str(wal))
        recovered.close()
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=5)


def test_forked_child_cannot_reuse_inherited_manager_or_drop_parent_lock(tmp_path: Path):
    wal = tmp_path / "forked.json"
    ready, gate, release, result = (tmp_path / name for name in ("fork.ready", "unused.gate", "unused.release", "fork.result"))
    worker = _spawn(tmp_path, "fork-check", wal, ready, gate, release, result)
    stdout, stderr = worker.communicate(timeout=10)
    assert worker.returncode == 0, (stdout, stderr)
    assert result.read_text() == "BLOCKED"


def test_advisor_partial_startup_cleans_earlier_owners_and_shutdown_releases_all(tmp_path: Path):
    wal_base = tmp_path / "advisor.json"
    sensex_wal = tmp_path / "advisor_sensex.json"
    external_sensex_owner = ActivePositionManager(wal_path=str(sensex_wal))
    with pytest.raises(WALOwnershipError, match="already owned"):
        SentinelLiveStreamAdvisor(wal_path=str(wal_base), enable_stdout=False)

    # The advisor acquired NIFTY before SENSEX failed and must have released NIFTY.
    standalone_nifty = ActivePositionManager(wal_path=str(wal_base))
    standalone_nifty.close()
    external_sensex_owner.close()

    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal_base), enable_stdout=False)
    assert set(advisor.apms) == {"NIFTY", "SENSEX", "BANKNIFTY"}
    result = advisor.shutdown_apm_wal_ownership()
    assert result == {"closed": ["NIFTY", "SENSEX", "BANKNIFTY"], "failures": [], "status": "STOPPED"}
    advisor.shutdown_apm_wal_ownership()
    reopened = SentinelLiveStreamAdvisor(wal_path=str(wal_base), enable_stdout=False)
    reopened.shutdown_apm_wal_ownership()


def test_wal_path_cannot_target_owner_lock_namespace_and_lock_inode_survives_replace(tmp_path: Path):
    wal = tmp_path / "trade.json"
    owner = ActivePositionManager(wal_path=str(wal))
    owner_lock = Path(owner._wal_lock_path)
    first_identity = owner_lock.stat()
    wal.write_text("not overwritten by a lock-path alias")
    before = wal.read_bytes()

    with pytest.raises(WALOwnershipError):
        ActivePositionManager(wal_path=str(owner_lock))

    assert wal.read_bytes() == before
    owner._persist_wal_atomic(force_sync=True)
    second_identity = owner_lock.stat()
    assert (second_identity.st_dev, second_identity.st_ino) == (first_identity.st_dev, first_identity.st_ino)
    assert wal.read_bytes() != before  # only the owner wrote its WAL snapshot
    with pytest.raises(WALOwnershipError, match="already owned"):
        ActivePositionManager(wal_path=str(wal))
    owner.close()


def test_independent_process_cannot_treat_owner_lock_as_wal_or_steal_owner(tmp_path: Path):
    wal = tmp_path / "trade.json"
    ready_a, unused_gate, unused_release, unused_result = (
        tmp_path / name for name in ("owner.ready", "unused.gate", "unused.release", "unused.result")
    )
    owner = _spawn(tmp_path, "hold", wal, ready_a, unused_gate, unused_release, unused_result)
    b = c = None
    try:
        _wait_for(ready_a, owner)
        owner_lock_path = Path(ready_a.read_text())
        # Exercise the legacy sidecar spelling, which the new implementation
        # preserves as an alias into the reserved namespace.
        legacy_sidecar_path = Path(str(wal) + ".lock")
        owner_lock_stat = owner_lock_path.stat()
        b_gate = tmp_path / "b.start"
        b_release = tmp_path / "b.release"
        b = _spawn(tmp_path, "contender", legacy_sidecar_path, tmp_path / "b.ready", b_gate, b_release, tmp_path / "b.result")
        _wait_for(tmp_path / "b.ready", b)
        b_gate.touch()
        _wait_for(tmp_path / "b.result", b)
        assert (tmp_path / "b.result").read_text().startswith("BLOCKED:")
        assert not wal.exists()  # rejected legacy lock alias did not create/replace A's WAL
        assert (owner_lock_path.stat().st_dev, owner_lock_path.stat().st_ino) == (
            owner_lock_stat.st_dev, owner_lock_stat.st_ino,
        )

        c_gate = tmp_path / "c.start"
        c_release = tmp_path / "c.release"
        c = _spawn(tmp_path, "contender", wal, tmp_path / "c.ready", c_gate, c_release, tmp_path / "c.result")
        _wait_for(tmp_path / "c.ready", c)
        c_gate.touch()
        _wait_for(tmp_path / "c.result", c)
        assert (tmp_path / "c.result").read_text().startswith("BLOCKED:APM WAL already owned")
        assert (owner_lock_path.stat().st_dev, owner_lock_path.stat().st_ino) == (
            owner_lock_stat.st_dev, owner_lock_stat.st_ino,
        )
    finally:
        for release_path in (tmp_path / "b.release", tmp_path / "c.release"):
            release_path.touch()
        if owner.poll() is None:
            owner.terminate()
        for process in (b, c, owner):
            if process is not None:
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)
    assert owner.returncode is not None
    assert b.returncode == 0
    assert c.returncode == 0


def test_relative_dotdot_parent_symlink_and_leaf_symlink_aliases_share_owner(tmp_path: Path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    actual = root / "state.json"
    parent_alias = tmp_path / "parent-alias"
    parent_alias.symlink_to(root, target_is_directory=True)
    leaf_alias = root / "leaf-alias.json"
    leaf_alias.symlink_to(actual)
    owner = ActivePositionManager(wal_path=str(actual))

    aliases = [
        parent_alias / "state.json",
        root / "subdir" / ".." / "state.json",
        leaf_alias,
    ]
    for alias in aliases:
        with pytest.raises(WALOwnershipError, match="already owned"):
            ActivePositionManager(wal_path=str(alias))

    monkeypatch.chdir(root)
    with pytest.raises(WALOwnershipError, match="already owned"):
        ActivePositionManager(wal_path="state.json")
    owner.close()


def test_hard_linked_wal_is_rejected_before_read_or_mutation(tmp_path: Path):
    wal = tmp_path / "hardlinked.json"
    alias = tmp_path / "hardlinked-alias.json"
    original = b'{"state":"STANDBY","payload":null}'
    wal.write_bytes(original)
    os.link(wal, alias)

    with pytest.raises(WALOwnershipError, match="hard-linked"):
        ActivePositionManager(wal_path=str(wal))
    with pytest.raises(WALOwnershipError, match="hard-linked"):
        ActivePositionManager(wal_path=str(alias))
    assert wal.read_bytes() == original
    assert alias.read_bytes() == original


def test_manager_rechecks_hard_link_before_atomic_persistence(tmp_path: Path):
    wal = tmp_path / "linked-after-acquire.json"
    owner = ActivePositionManager(wal_path=str(wal))
    owner._persist_wal_atomic(force_sync=True)
    alias = tmp_path / "linked-after-acquire-alias.json"
    os.link(wal, alias)
    original = wal.read_bytes()

    try:
        with pytest.raises(WALOwnershipError, match="hard-linked"):
            owner._persist_wal_atomic(force_sync=True)
        assert wal.read_bytes() == original
        assert alias.read_bytes() == original
    finally:
        owner.close()


def test_reserved_lock_directory_symlink_is_rejected_before_wal_recovery(tmp_path: Path):
    wal = tmp_path / "unsafe.json"
    original = b'{"state":'
    wal.write_bytes(original)
    lock_dir = tmp_path / ".apm_wal_locks"
    outside = tmp_path / "outside-locks"
    outside.mkdir()
    lock_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(WALOwnershipError, match="lock namespace"):
        ActivePositionManager(wal_path=str(wal))
    assert wal.read_bytes() == original


def test_unsupported_flock_and_nofollow_fail_before_wal_mutation(tmp_path: Path, monkeypatch):
    import core.active_position_manager as apm_module

    wal = tmp_path / "unsupported.json"
    original = b'{"state":'
    wal.write_bytes(original)
    monkeypatch.setattr(apm_module, "fcntl", None)
    with pytest.raises(WALOwnershipError, match="flock is unsupported"):
        ActivePositionManager(wal_path=str(wal))
    assert wal.read_bytes() == original

    monkeypatch.undo()
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    with pytest.raises(WALOwnershipError, match="safe O_NOFOLLOW open is unsupported"):
        ActivePositionManager(wal_path=str(wal))
    assert wal.read_bytes() == original


def test_lock_open_and_flock_failures_do_not_mutate_wal(tmp_path: Path, monkeypatch):
    import core.active_position_manager as apm_module

    wal = tmp_path / "lock-failures.json"
    original = b'{"state":'
    wal.write_bytes(original)
    real_open = os.open

    def fail_owner_lock_open(path, flags, *args, **kwargs):
        if str(path).endswith(".lock") or ".apm_wal_locks" in str(path):
            raise OSError(errno.EACCES, "injected lock open denial")
        return real_open(path, flags, *args, **kwargs)

    import errno
    monkeypatch.setattr(apm_module.os, "open", fail_owner_lock_open)
    with pytest.raises(WALOwnershipError, match="lock namespace open failed|owner lock open failed"):
        ActivePositionManager(wal_path=str(wal))
    assert wal.read_bytes() == original

    monkeypatch.setattr(apm_module.os, "open", real_open)
    if apm_module.fcntl is None:
        pytest.skip("flock unavailable on this platform")
    monkeypatch.setattr(
        apm_module.fcntl, "flock",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError(errno.EIO, "injected flock failure")),
    )
    with pytest.raises(WALOwnershipError, match="flock failed"):
        ActivePositionManager(wal_path=str(wal))
    assert wal.read_bytes() == original


def test_existing_regular_legacy_sidecar_is_preserved_and_blocks_before_recovery(tmp_path: Path):
    wal = tmp_path / "legacy-regular.json"
    original_wal = b'{"state":'
    wal.write_bytes(original_wal)
    legacy = Path(str(wal) + ".lock")
    original_sidecar = b"legacy lock contents must remain byte-identical"
    legacy.write_bytes(original_sidecar)
    legacy.chmod(0o640)
    fixed_ns = 1_700_000_000_123_456_789
    os.utime(legacy, ns=(fixed_ns, fixed_ns))
    before = legacy.stat()

    with pytest.raises(WALOwnershipError, match="occupied by a non-alias file"):
        ActivePositionManager(wal_path=str(wal))

    after = legacy.stat()
    assert legacy.read_bytes() == original_sidecar
    assert (after.st_dev, after.st_ino, after.st_mode, after.st_mtime_ns) == (
        before.st_dev, before.st_ino, before.st_mode, before.st_mtime_ns,
    )
    assert wal.read_bytes() == original_wal


@pytest.mark.parametrize("legacy_kind", ["wrong-target-symlink", "directory"])
def test_existing_nonalias_legacy_sidecar_object_is_preserved(tmp_path: Path, legacy_kind: str):
    wal = tmp_path / f"legacy-{legacy_kind}.json"
    original_wal = b'{"state":'
    wal.write_bytes(original_wal)
    legacy = Path(str(wal) + ".lock")
    target = tmp_path / "unrelated-lock-target"
    if legacy_kind == "wrong-target-symlink":
        target.write_bytes(b"unrelated target remains unchanged")
        legacy.symlink_to(target)
    else:
        legacy.mkdir()
        (legacy / "sentinel").write_bytes(b"directory contents remain unchanged")
    before = os.lstat(legacy)
    link_text = os.readlink(legacy) if stat.S_ISLNK(before.st_mode) else None

    with pytest.raises(WALOwnershipError):
        ActivePositionManager(wal_path=str(wal))

    after = os.lstat(legacy)
    assert (after.st_dev, after.st_ino, after.st_mode, after.st_mtime_ns) == (
        before.st_dev, before.st_ino, before.st_mode, before.st_mtime_ns,
    )
    assert (os.readlink(legacy) if stat.S_ISLNK(after.st_mode) else None) == link_text
    if legacy_kind == "wrong-target-symlink":
        assert target.read_bytes() == b"unrelated target remains unchanged"
    else:
        assert (legacy / "sentinel").read_bytes() == b"directory contents remain unchanged"
    assert wal.read_bytes() == original_wal


def test_legacy_alias_symlink_is_valid_but_old_nofollow_open_fails(tmp_path: Path):
    wal = tmp_path / "legacy-alias.json"
    owner = ActivePositionManager(wal_path=str(wal))
    legacy = Path(str(wal) + ".lock")
    assert legacy.is_symlink()
    assert legacy.resolve(strict=True) == owner._wal_lock_path

    with pytest.raises(OSError) as exc_info:
        os.open(str(legacy), os.O_RDONLY | os.O_NOFOLLOW)
    assert exc_info.value.errno == errno.ELOOP
    owner.close()


def test_persistent_enoent_lock_open_fails_closed_without_sidecar_fallback(tmp_path: Path, monkeypatch):
    import core.active_position_manager as apm_module

    wal = tmp_path / "injected-enoent.json"
    original = b'{"state":'
    wal.write_bytes(original)
    real_open = os.open
    attempts = 0

    def missing_lock_entry(path, flags, *args, **kwargs):
        nonlocal attempts
        if kwargs.get("dir_fd") is not None:
            attempts += 1
            raise FileNotFoundError(errno.ENOENT, "injected missing lock entry", str(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(apm_module.os, "open", missing_lock_entry)
    with pytest.raises(WALOwnershipError, match=r"owner lock open failed at .* \(2\)"):
        ActivePositionManager(wal_path=str(wal))
    assert attempts == 2  # one retry, gated by same-parent/same-directory identity
    assert wal.read_bytes() == original
    assert not Path(str(wal) + ".lock").exists()  # no unsafe sibling-lock fallback


def test_transient_enoent_retries_only_after_namespace_identity_check(tmp_path: Path, monkeypatch):
    import core.active_position_manager as apm_module

    wal = tmp_path / "transient-enoent.json"
    real_open = os.open
    attempts = 0

    def one_transient_missing_entry(path, flags, *args, **kwargs):
        nonlocal attempts
        if kwargs.get("dir_fd") is not None:
            attempts += 1
            if attempts == 1:
                raise FileNotFoundError(errno.ENOENT, "injected transient lock entry", str(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(apm_module.os, "open", one_transient_missing_entry)
    owner = ActivePositionManager(wal_path=str(wal))
    try:
        assert attempts == 2
        assert Path(str(wal) + ".lock").is_symlink()
        owner._assert_wal_lock_identity()
    finally:
        owner.close()


def test_enoent_retry_fails_if_lock_directory_identity_changed(tmp_path: Path, monkeypatch):
    import core.active_position_manager as apm_module

    wal = tmp_path / "changed-lock-dir.json"
    original = b'{"state":'
    wal.write_bytes(original)
    real_open = os.open
    attempts = 0
    lock_dir = tmp_path / ".apm_wal_locks"

    def replace_directory_then_report_missing(path, flags, *args, **kwargs):
        nonlocal attempts
        if kwargs.get("dir_fd") is not None:
            attempts += 1
            lock_dir.rename(tmp_path / ".apm_wal_locks-displaced")
            lock_dir.mkdir(mode=0o700)
            raise FileNotFoundError(errno.ENOENT, "injected changed namespace", str(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(apm_module.os, "open", replace_directory_then_report_missing)
    with pytest.raises(WALOwnershipError, match=r"owner lock open failed \(2\).*namespace revalidation failed.*identity changed"):
        ActivePositionManager(wal_path=str(wal))
    assert attempts == 1  # identity mismatch forbids retry
    assert wal.read_bytes() == original
    assert not Path(str(wal) + ".lock").exists()

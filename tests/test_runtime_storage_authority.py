from pathlib import Path

import pytest

from core.runtime_storage_authority import StorageAuthorityError, assert_same_device, establish, final_seal_status, revalidate


def test_runtime_root_must_be_below_real_volume(tmp_path: Path):
    with pytest.raises(StorageAuthorityError, match="mount_absent"):
        establish(volume=tmp_path / "missing", runtime_root=tmp_path / "run")


def test_mount_probe_is_required_before_mountpoint_creation(tmp_path: Path, monkeypatch):
    volume = tmp_path / "TradeBotData"
    runtime = volume / "session"
    volume.mkdir()
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ())
    with pytest.raises(StorageAuthorityError, match="mount_absent"):
        establish(volume=volume, runtime_root=runtime)
    assert not runtime.exists()


def test_external_probe_accepts_same_device_directory(tmp_path: Path, monkeypatch):
    volume = tmp_path / "TradeBotData"
    volume.mkdir()
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ("device on /Volumes/TradeBotData (apfs)",))
    result = establish(volume=volume, runtime_root=volume / "session")
    assert result.device_id == volume.stat().st_dev
    assert result.runtime_root == (volume / "session").resolve()


def test_revalidate_rejects_device_change(tmp_path: Path, monkeypatch):
    volume = tmp_path / "TradeBotData"
    volume.mkdir()
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ("device on /Volumes/TradeBotData (apfs)",))
    authority = establish(volume=volume, runtime_root=volume / "session")
    changed = authority.__class__(authority.volume, authority.runtime_root, authority.device_id + 1)
    with pytest.raises(StorageAuthorityError, match="device_changed"):
        revalidate(changed)


def test_revalidate_rejects_mount_loss(tmp_path: Path, monkeypatch):
    volume = tmp_path / "TradeBotData"
    volume.mkdir()
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ("mounted",))
    authority = establish(volume=volume, runtime_root=volume / "session")
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ())
    with pytest.raises(StorageAuthorityError, match="mount_absent"):
        revalidate(authority)


def test_internal_runtime_root_is_rejected(tmp_path: Path, monkeypatch):
    volume = tmp_path / "TradeBotData"
    volume.mkdir()
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ("mounted",))
    with pytest.raises(StorageAuthorityError, match="runtime_escape"):
        establish(volume=volume, runtime_root=tmp_path / "internal")


def test_symlinked_runtime_root_cannot_escape(tmp_path: Path, monkeypatch):
    volume = tmp_path / "TradeBotData"
    outside = tmp_path / "outside"
    volume.mkdir()
    outside.mkdir()
    (volume / "session").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ("mounted",))
    with pytest.raises(StorageAuthorityError, match="runtime_escape"):
        establish(volume=volume, runtime_root=volume / "session")


def test_revalidate_rejects_statvfs_failure(tmp_path: Path, monkeypatch):
    volume = tmp_path / "TradeBotData"
    volume.mkdir()
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ("mounted",))
    authority = establish(volume=volume, runtime_root=volume / "session")
    monkeypatch.setattr("core.runtime_storage_authority.os.statvfs", lambda _: (_ for _ in ()).throw(OSError("statvfs")))
    with pytest.raises(StorageAuthorityError, match="OSError"):
        revalidate(authority)


def test_revalidate_rejects_temp_probe_failure(tmp_path: Path, monkeypatch):
    volume = tmp_path / "TradeBotData"
    volume.mkdir()
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ("mounted",))
    authority = establish(volume=volume, runtime_root=volume / "session")
    monkeypatch.setattr("core.runtime_storage_authority.tempfile.NamedTemporaryFile", lambda **_: (_ for _ in ()).throw(OSError("temp")))
    with pytest.raises(StorageAuthorityError, match="OSError"):
        revalidate(authority)


def test_material_target_must_share_authority_device(tmp_path: Path, monkeypatch):
    volume = tmp_path / "TradeBotData"
    volume.mkdir()
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ("mounted",))
    authority = establish(volume=volume, runtime_root=volume / "session")
    target = volume / "session" / "artifact.json"
    target.parent.mkdir(exist_ok=True)
    assert_same_device(authority, target)
    foreign = authority.__class__(authority.volume, authority.runtime_root, authority.device_id + 1)
    with pytest.raises(StorageAuthorityError, match="material_device_mismatch"):
        assert_same_device(foreign, target)


def test_symlinked_material_target_is_rejected(tmp_path: Path, monkeypatch):
    volume = tmp_path / "TradeBotData"
    outside = tmp_path / "outside"
    volume.mkdir()
    outside.mkdir()
    (outside / "artifact.json").write_text("x")
    (volume / "artifact.json").symlink_to(outside / "artifact.json")
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ("mounted",))
    authority = establish(volume=volume, runtime_root=volume / "session")
    with pytest.raises(StorageAuthorityError, match="path_escape"):
        assert_same_device(authority, volume / "artifact.json")


@pytest.mark.parametrize(
    ("storage_lost", "drain_complete", "expected"),
    [(True, True, "UNAVAILABLE_DUE_STORAGE_LOSS"), (True, False, "UNAVAILABLE_DUE_STORAGE_LOSS"), (False, True, "PASS"), (False, False, "PARTIAL")],
)
def test_storage_loss_never_claims_successful_seal(storage_lost, drain_complete, expected):
    assert final_seal_status(storage_lost=storage_lost, drain_complete=drain_complete) == expected

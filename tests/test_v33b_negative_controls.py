"""V33B A-R storage controls; faults are injected, never applied to the host mount."""
from pathlib import Path
import pytest

from core.runtime_storage_authority import StorageAuthorityError, assert_same_device, establish, final_seal_status, revalidate


def mounted(tmp_path, monkeypatch):
    volume = tmp_path / "TradeBotData"
    volume.mkdir()
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ("dev on /Volumes/TradeBotData (apfs)",))
    return volume


def test_A_correct_external_mount(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch)
    authority = establish(volume=volume, runtime_root=volume / "session")
    assert authority.device_id == volume.stat().st_dev


def test_B_mount_absent(tmp_path, monkeypatch):
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ())
    with pytest.raises(StorageAuthorityError, match="mount_absent"):
        establish(volume=tmp_path / "missing", runtime_root=tmp_path / "run")


def test_C_ordinary_directory_mountpoint(tmp_path, monkeypatch):
    volume = tmp_path / "TradeBotData"; volume.mkdir()
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ())
    with pytest.raises(StorageAuthorityError, match="mount_absent"):
        establish(volume=volume, runtime_root=volume / "run")


def test_D_wrong_device(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch)
    authority = establish(volume=volume, runtime_root=volume / "run")
    with pytest.raises(StorageAuthorityError, match="material_device_mismatch"):
        assert_same_device(authority.__class__(authority.volume, authority.runtime_root, authority.device_id + 1), volume / "run" / "x")


def test_E_internal_runtime_root(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch)
    with pytest.raises(StorageAuthorityError, match="runtime_escape"):
        establish(volume=volume, runtime_root=tmp_path / "internal")


def test_F_internal_temp(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch)
    authority = establish(volume=volume, runtime_root=volume / "run")
    (tmp_path / "internal").mkdir()
    with pytest.raises(StorageAuthorityError, match="path_escape"):
        assert_same_device(authority, tmp_path / "internal" / "temp")


def test_G_cross_device_atomic(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch)
    authority = establish(volume=volume, runtime_root=volume / "run")
    with pytest.raises(StorageAuthorityError, match="material_device_mismatch"):
        assert_same_device(authority.__class__(authority.volume, authority.runtime_root, authority.device_id + 1), volume / "run" / "artifact")


def test_H_read_only_volume(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch)
    monkeypatch.setattr("core.runtime_storage_authority.tempfile.NamedTemporaryFile", lambda **_: (_ for _ in ()).throw(OSError("read_only")))
    with pytest.raises(StorageAuthorityError, match="OSError"):
        establish(volume=volume, runtime_root=volume / "run")


def test_I_statvfs_failure(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch)
    monkeypatch.setattr("core.runtime_storage_authority.os.statvfs", lambda _: (_ for _ in ()).throw(OSError("statvfs")))
    with pytest.raises(StorageAuthorityError, match="OSError"):
        establish(volume=volume, runtime_root=volume / "run")


def test_J_mount_disappears_after_start(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch); authority = establish(volume=volume, runtime_root=volume / "run")
    monkeypatch.setattr("core.runtime_storage_authority._mounted_paths", lambda: ())
    with pytest.raises(StorageAuthorityError, match="mount_absent"): revalidate(authority)


def test_K_device_changes_after_start(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch); authority = establish(volume=volume, runtime_root=volume / "run")
    changed = authority.__class__(authority.volume, authority.runtime_root, authority.device_id + 1)
    with pytest.raises(StorageAuthorityError, match="device_changed"): revalidate(changed)


def test_L_repository_logs_fallback(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch); authority = establish(volume=volume, runtime_root=volume / "run")
    with pytest.raises(StorageAuthorityError, match="path_escape"): assert_same_device(authority, Path("/Users/madhuram/tradebot/logs/x"))


def test_M_cwd_logs_fallback(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch); authority = establish(volume=volume, runtime_root=volume / "run")
    with pytest.raises(StorageAuthorityError, match="path_escape"): assert_same_device(authority, Path("logs/x"))


def test_N_system_temp_fallback(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch); authority = establish(volume=volume, runtime_root=volume / "run")
    with pytest.raises(StorageAuthorityError, match="path_escape"): assert_same_device(authority, Path("/tmp/x"))


def test_O_parquet_internal_temp(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch); authority = establish(volume=volume, runtime_root=volume / "run")
    with pytest.raises(StorageAuthorityError, match="path_escape"): assert_same_device(authority, Path("/private/tmp/x"))


def test_P_optional_symlink_escape(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch); outside = tmp_path / "outside"; outside.mkdir(); (volume / "link").symlink_to(outside, target_is_directory=True)
    authority = establish(volume=volume, runtime_root=volume / "run")
    with pytest.raises(StorageAuthorityError, match="path_escape"): assert_same_device(authority, volume / "link" / "x")


def test_Q_runtime_symlink_escape(tmp_path, monkeypatch):
    volume = mounted(tmp_path, monkeypatch); outside = tmp_path / "outside"; outside.mkdir(); (volume / "run").symlink_to(outside, target_is_directory=True)
    with pytest.raises(StorageAuthorityError, match="runtime_escape"): establish(volume=volume, runtime_root=volume / "run")


def test_R_finalization_after_storage_loss(tmp_path):
    assert final_seal_status(storage_lost=True, drain_complete=True) == "UNAVAILABLE_DUE_STORAGE_LOSS"

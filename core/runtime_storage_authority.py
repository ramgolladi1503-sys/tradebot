"""Fail-closed authority checks for governed external runtime storage."""
from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path


class StorageAuthorityError(RuntimeError):
    pass


def final_seal_status(*, storage_lost: bool, drain_complete: bool) -> str:
    if storage_lost:
        return "UNAVAILABLE_DUE_STORAGE_LOSS"
    return "PASS" if drain_complete else "PARTIAL"


@dataclass(frozen=True)
class StorageAuthority:
    volume: Path
    runtime_root: Path
    device_id: int


def assert_same_device(authority: StorageAuthority, *paths: Path) -> None:
    """Reject material paths whose resolved parent is not on the authority device."""
    for raw in paths:
        path = Path(raw).expanduser()
        probe = path if path.exists() else path.parent
        try:
            resolved = probe.resolve(strict=True)
            if os.path.commonpath((str(authority.volume), str(resolved))) != str(authority.volume):
                raise StorageAuthorityError("RUNTIME_STORAGE_AUTHORITY_LOST:path_escape")
            if resolved.stat().st_dev != authority.device_id:
                raise StorageAuthorityError("RUNTIME_STORAGE_AUTHORITY_LOST:material_device_mismatch")
        except StorageAuthorityError:
            raise
        except OSError as exc:
            raise StorageAuthorityError(f"RUNTIME_STORAGE_AUTHORITY_LOST:path_stat:{type(exc).__name__}") from exc


def _mounted_paths() -> tuple[str, ...]:
    if os.name != "posix":
        return ()
    try:
        output = os.popen("mount").read()
    except OSError:
        return ()
    return tuple(line for line in output.splitlines() if " on /Volumes/TradeBotData " in line)


def establish(*, volume: Path, runtime_root: Path) -> StorageAuthority:
    """Validate mount, realpath, device, writability, and same-device temp.

    This function never creates the mountpoint. It may create only a child
    runtime directory after the mount itself has been positively established.
    """
    volume = Path(volume).expanduser()
    runtime_root = Path(runtime_root).expanduser()
    if not volume.is_dir() or not _mounted_paths():
        raise StorageAuthorityError("RUNTIME_STORAGE_AUTHORITY_LOST:mount_absent")
    try:
        volume_real = volume.resolve(strict=True)
        volume_stat = volume_real.stat()
    except OSError as exc:
        raise StorageAuthorityError("RUNTIME_STORAGE_AUTHORITY_LOST:volume_stat") from exc
    if not stat.S_ISDIR(volume_stat.st_mode):
        raise StorageAuthorityError("RUNTIME_STORAGE_AUTHORITY_LOST:volume_not_directory")
    if runtime_root.exists():
        runtime_real = runtime_root.resolve(strict=True)
    else:
        parent = runtime_root.parent.resolve(strict=True)
        runtime_real = parent / runtime_root.name
    try:
        if os.path.commonpath((str(volume_real), str(runtime_real))) != str(volume_real):
            raise StorageAuthorityError("RUNTIME_STORAGE_AUTHORITY_LOST:runtime_escape")
        runtime_root.mkdir(parents=True, exist_ok=True)
        runtime_stat = runtime_root.resolve(strict=True).stat()
        if runtime_stat.st_dev != volume_stat.st_dev:
            raise StorageAuthorityError("RUNTIME_STORAGE_AUTHORITY_LOST:device_mismatch")
        with tempfile.NamedTemporaryFile(dir=runtime_root, prefix=".storage-probe-", delete=True):
            pass
        os.statvfs(runtime_root)
    except StorageAuthorityError:
        raise
    except OSError as exc:
        raise StorageAuthorityError(f"RUNTIME_STORAGE_AUTHORITY_LOST:{type(exc).__name__}") from exc
    return StorageAuthority(volume_real, runtime_root.resolve(), int(volume_stat.st_dev))


def bind_environment(authority: StorageAuthority) -> None:
    """Bind dynamic path resolution to one externally-authorized runtime root."""
    root = str(authority.runtime_root)
    os.environ.update({
        "DATA_ROOT": root,
        "LOG_DIR": str(authority.runtime_root / "logs"),
        "REPO_LOG_DIR": str(authority.runtime_root / "logs"),
    })


def revalidate(authority: StorageAuthority) -> None:
    """Recheck an established authority without creating or falling back."""
    try:
        if not authority.volume.is_dir() or not _mounted_paths():
            raise StorageAuthorityError("RUNTIME_STORAGE_AUTHORITY_LOST:mount_absent")
        volume = authority.volume.resolve(strict=True)
        runtime = authority.runtime_root.resolve(strict=True)
        if volume != authority.volume or runtime != authority.runtime_root:
            raise StorageAuthorityError("RUNTIME_STORAGE_AUTHORITY_LOST:realpath_changed")
        if volume.stat().st_dev != authority.device_id or runtime.stat().st_dev != authority.device_id:
            raise StorageAuthorityError("RUNTIME_STORAGE_AUTHORITY_LOST:device_changed")
        os.statvfs(runtime)
        with tempfile.NamedTemporaryFile(dir=runtime, prefix=".storage-revalidate-", delete=True):
            pass
    except StorageAuthorityError:
        raise
    except OSError as exc:
        raise StorageAuthorityError(f"RUNTIME_STORAGE_AUTHORITY_LOST:{type(exc).__name__}") from exc

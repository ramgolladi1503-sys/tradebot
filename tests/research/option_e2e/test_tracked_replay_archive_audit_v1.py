from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path

import pytest

from research.option_e2e_recertification_v4.tracked_replay_archive_audit_v1.audit import (
    ArchiveHashMismatchError,
    UnsafeArchiveError,
    audit_tracked_archive,
)
from research.option_e2e_recertification_v4.tracked_replay_archive_audit_v1.oracle import (
    oracle_archive_facts,
    reconcile_primary_oracle,
)


def _zip(path: Path, members: dict[str, bytes]) -> str:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_audit_classifies_replay_archive_without_authority(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "replay.zip"
    digest = _zip(
        archive,
        {
            "underlying/NIFTY.parquet": b"PAR1x",
            "manifests/fetch_manifest.json": json.dumps(
                {"provider": "upstox", "files": 1}
            ).encode(),
        },
    )

    result = audit_tracked_archive(archive, expected_sha256=digest)

    assert result["source_disposition"] == "ARCHIVE_REPLAY_INPUT_ONLY"
    assert result["canonical_signal_source_count"] == 0
    assert result["canonical_dataset_source_count"] == 0
    assert result["market_data_parquet_member_count"] == 1
    assert result["source_manifest_member_count"] == 1
    assert result["allowed_for_live_execution"] is False


def test_wrong_physical_hash_fails(tmp_path: Path) -> None:
    archive = tmp_path / "replay.zip"
    _zip(archive, {"data.txt": b"x"})

    with pytest.raises(ArchiveHashMismatchError):
        audit_tracked_archive(archive, expected_sha256="0" * 64)


def test_path_traversal_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "replay.zip"
    digest = _zip(archive, {"../escape.json": b"{}"})

    with pytest.raises(UnsafeArchiveError):
        audit_tracked_archive(archive, expected_sha256=digest)


def test_symlink_member_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "replay.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        handle.writestr(info, "target")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    with pytest.raises(UnsafeArchiveError):
        audit_tracked_archive(archive, expected_sha256=digest)


def test_denied_member_is_not_opened(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "replay.zip"
    digest = _zip(
        archive,
        {
            "outcomes/realized_pnl.json": b'{"pnl":100}',
            "safe/manifest.json": b"{}",
        },
    )
    original = zipfile.ZipFile.open

    def guarded(self, name, *args, **kwargs):  # type: ignore[no-untyped-def]
        candidate = name.filename if isinstance(name, zipfile.ZipInfo) else str(name)
        if "outcomes" in candidate:
            raise AssertionError("denied member opened")
        return original(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", guarded)
    result = audit_tracked_archive(archive, expected_sha256=digest)

    denied = next(item for item in result["members"] if item["denied_by_policy"])
    assert denied["content_opened"] is False
    assert result["outcomes_read"] is False
    assert result["pnl_read"] is False


def test_primary_and_independent_oracle_agree(tmp_path: Path) -> None:
    archive = tmp_path / "replay.zip"
    digest = _zip(
        archive,
        {"manifests/fetch_manifest.json": b'{"source":"upstox"}'},
    )

    primary = audit_tracked_archive(archive, expected_sha256=digest)
    oracle = oracle_archive_facts(archive, expected_sha256=digest)
    agreement = reconcile_primary_oracle(primary, oracle)

    assert agreement["status"] == "AGREEMENT"
    assert all(agreement["checks"].values())


def test_audit_is_semantically_deterministic(tmp_path: Path) -> None:
    archive = tmp_path / "replay.zip"
    digest = _zip(
        archive,
        {"manifests/fetch_manifest.json": b'{"source":"upstox"}'},
    )

    first = audit_tracked_archive(archive, expected_sha256=digest)
    second = audit_tracked_archive(archive, expected_sha256=digest)

    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        second,
        sort_keys=True,
        separators=(",", ":"),
    )

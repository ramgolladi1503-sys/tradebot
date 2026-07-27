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
from research.option_e2e_recertification_v4.tracked_replay_archive_audit_v1.build_evidence import (
    build,
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
            "replay/20260709/underlying/NIFTY.parquet": b"PAR1x",
            "replay/20260709/manifests/fetch_manifest.json": json.dumps(
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
    assert result["represented_date_directory_count"] == 1
    assert result["dates_with_parquet_member_count"] == 1
    assert result["allowed_for_live_execution"] is False


def test_appledouble_metadata_is_counted_but_never_opened(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "replay.zip"
    digest = _zip(
        archive,
        {
            "__MACOSX/replay/._NIFTY.parquet": b"metadata",
            "replay/20260709/underlying/NIFTY.parquet": b"PAR1x",
        },
    )
    original = zipfile.ZipFile.open

    def guarded(self, name, *args, **kwargs):  # type: ignore[no-untyped-def]
        candidate = name.filename if isinstance(name, zipfile.ZipInfo) else str(name)
        if candidate.startswith("__MACOSX/"):
            raise AssertionError("archive metadata opened")
        return original(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", guarded)
    result = audit_tracked_archive(archive, expected_sha256=digest)

    metadata = next(item for item in result["members"] if item["archive_metadata"])
    assert metadata["candidate_class"] == "ARCHIVE_METADATA_MEMBER"
    assert metadata["content_opened"] is False
    assert result["archive_metadata_member_count"] == 1
    assert result["content_tree_member_count"] == 1
    assert result["opened_member_count"] == 1
    assert result["market_data_parquet_member_count"] == 1


def test_option_like_parquets_exclude_appledouble_copies(tmp_path: Path) -> None:
    archive = tmp_path / "replay.zip"
    digest = _zip(
        archive,
        {
            "__MACOSX/replay/20260709/underlying/._NIFTY 24000 CE.parquet": b"x",
            "replay/20260709/underlying/NIFTY 24000 CE.parquet": b"PAR1x",
            "replay/20260709/underlying/NIFTY 24000 PE.parquet": b"PAR1y",
        },
    )

    result = audit_tracked_archive(archive, expected_sha256=digest)

    assert result["market_data_parquet_member_count"] == 2
    assert result["option_like_parquet_member_count"] == 2
    assert result["archive_metadata_member_count"] == 1


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
        {
            "__MACOSX/replay/._manifest.json": b"metadata",
            "replay/manifests/fetch_manifest.json": b'{"source":"upstox"}',
        },
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


def test_builder_publishes_compact_hash_bound_evidence(tmp_path: Path) -> None:
    archive = tmp_path / "replay.zip"
    digest = _zip(
        archive,
        {
            "__MACOSX/replay/._manifest.json": b"metadata",
            "replay/20260709/manifests/fetch_manifest.json": b"{}",
        },
    )
    output_dir = tmp_path / "out"
    build(archive, output_dir, expected_sha256=digest)

    compact = json.loads(
        (output_dir / "tracked_replay_archive_audit_compact.json").read_text()
    )
    manifest = json.loads((output_dir / "external_evidence_manifest.json").read_text())
    assert "members" not in compact
    assert compact["member_registry_semantic_sha256"]
    assert compact["candidate_class_counts"] == {
        "ARCHIVE_METADATA_MEMBER": 1,
        "SOURCE_MANIFEST_MEMBER": 1,
    }
    assert manifest["full_member_registry_committed"] is False
    for path in output_dir.glob("*.json"):
        sidecar = path.with_suffix(path.suffix + ".sha256")
        assert sidecar.is_file()
        assert sidecar.read_text().split()[0] == hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from research.option_e2e_recertification_v4.expired_option_replay_v1.archive_source import (
    prepare_option_source,
)
from research.option_e2e_recertification_v4.expired_option_replay_v1.engine import (
    ReplayDataError,
)


def _write_valid_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "upstox-expired-options-v1/raw/responses/NIFTY/expiry=2026-07-21/contracts.json",
            json.dumps({"data": []}),
        )


def test_prepare_option_source_discovers_single_wrapped_root(tmp_path: Path) -> None:
    archive_path = tmp_path / "options.zip"
    _write_valid_zip(archive_path)

    prepared = prepare_option_source(archive_path)
    try:
        assert prepared.source_kind == "zip"
        assert prepared.extracted is True
        assert prepared.source_sha256 != ""
        assert prepared.root.name == "upstox-expired-options-v1"
        assert (prepared.root / "raw" / "responses").is_dir()
    finally:
        extracted_root = prepared.temporary_root
        prepared.cleanup()

    assert extracted_root is not None
    assert not extracted_root.exists()


def test_prepare_option_source_rejects_zip_slip(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", "bad")

    with pytest.raises(ReplayDataError, match="unsafe_zip_member"):
        prepare_option_source(archive_path)


def test_prepare_option_source_accepts_directory_without_extraction(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dataset"
    (root / "raw" / "responses").mkdir(parents=True)

    prepared = prepare_option_source(root)

    assert prepared.root == root.resolve()
    assert prepared.source_kind == "directory"
    assert prepared.extracted is False
    assert prepared.temporary_root is None

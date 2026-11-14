from __future__ import annotations

from pathlib import Path

import pytest

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    CurrentRoot,
    assert_no_overlaps,
    legacy_reconstruction,
)
from research.option_e2e_recertification_v4.current_certification_source_universe_v1.oracle import (
    recompute_legacy_disposition,
)
from research.option_e2e_recertification_v4.local_unresolved_source_audit_v1.build_evidence import (
    load_root_manifest,
)


def test_legacy_missing_paths_cannot_claim_reproducible() -> None:
    payload = legacy_reconstruction()

    oracle = recompute_legacy_disposition(payload)

    expected = {
        "prior_root_count": 27,
        "exact_paths_recovered": 0,
        "oracle_verdict": "LEGACY_27_ROOT_CENSUS_NON_REPRODUCIBLE_MISSING_PATH_BINDINGS",
        "primary_oracle_agreement": "AGREEMENT",
    }
    observed = {
        "prior_root_count": payload["prior_root_count"],
        "exact_paths_recovered": payload["exact_paths_recovered"],
        "oracle_verdict": oracle["oracle_verdict"],
        "primary_oracle_agreement": oracle["primary_oracle_agreement"],
    }
    assert observed == expected


def test_duplicate_or_nested_current_roots_fail(tmp_path: Path) -> None:
    parent = tmp_path / "root"
    child = parent / "child"
    child.mkdir(parents=True)

    roots = [
        CurrentRoot("PARENT", "EXTERNAL", parent, ("DATA",), "test"),
        CurrentRoot("CHILD", "EXTERNAL", child, ("DATA",), "test"),
    ]

    with pytest.raises(ValueError, match="overlapping_physical_roots"):
        assert_no_overlaps(roots)


def test_root_manifest_loader_accepts_machine_manifest(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        '{"roots":[{"current_root_id":"ROOT_A","absolute_path":"%s"}]}' % root.as_posix(),
        encoding="utf-8",
    )

    specs = load_root_manifest(manifest)

    observed = [(spec.root_id, spec.path) for spec in specs]
    assert observed == [("ROOT_A", root)]

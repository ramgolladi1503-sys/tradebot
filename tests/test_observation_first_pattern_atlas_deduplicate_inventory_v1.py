from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_observation_first_pattern_atlas_deduplicate_inventory_v1.py"
SPEC = importlib.util.spec_from_file_location("atlas_dedup", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_sha_duplicates_are_skipped_deterministically() -> None:
    unique, duplicates = MODULE.deduplicate([
        {"path": "z.parquet", "sha256": "same"},
        {"path": "a.parquet", "sha256": "same"},
        {"path": "b.parquet", "sha256": "different"},
    ])
    assert [item["path"] for item in unique] == ["a.parquet", "b.parquet"]
    assert duplicates == [{"path": "z.parquet", "duplicate_of": "a.parquet", "identity": "same"}]


def test_missing_sha_falls_back_to_path_identity() -> None:
    unique, duplicates = MODULE.deduplicate([{"path": "a"}, {"path": "b"}])
    assert len(unique) == 2
    assert duplicates == []

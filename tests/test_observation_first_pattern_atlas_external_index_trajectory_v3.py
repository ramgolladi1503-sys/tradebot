from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_observation_first_pattern_atlas_external_index_trajectory_v3.py"
)
SPEC = importlib.util.spec_from_file_location("atlas_external_index_v3", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_external_source_fails_closed_on_size_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.parquet"
    source.write_bytes(b"not parquet")
    with pytest.raises(ValueError, match="size mismatch"):
        MODULE.inspect_external_parquet(
            source,
            digest(source),
            source.stat().st_size + 1,
            "constituent_index_5m.parquet",
        )


def test_external_source_fails_closed_on_sha_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.parquet"
    source.write_bytes(b"not parquet")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        MODULE.inspect_external_parquet(
            source,
            "0" * 64,
            source.stat().st_size,
            "constituent_index_5m.parquet",
        )


def test_real_external_parquet_is_inspected_in_place(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    source = tmp_path / "physical-object-without-repo-checkout.parquet"
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-02 09:15", periods=3, freq="5min"),
            "symbol": ["NIFTY", "NIFTY", "NIFTY"],
            "close": [25000.0, 25005.0, 25010.0],
        }
    )
    frame.to_parquet(source, index=False)
    source_sha = MODULE.sha256_file(source)
    evidence = MODULE.inspect_external_parquet(
        source,
        source_sha,
        source.stat().st_size,
        "constituent_index_5m.parquet",
    )
    assert evidence["path"] == str(source.resolve())
    assert evidence["sha256"] == source_sha
    assert evidence["size_bytes"] == source.stat().st_size
    assert evidence["rows"] == 3
    assert evidence["storage_mode"] == "shared_external_physical_file"
    assert evidence["outcome_like_columns"] == []

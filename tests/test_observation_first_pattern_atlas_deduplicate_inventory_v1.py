from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_observation_first_pattern_atlas_deduplicate_inventory_v1.py"
)


def run_cli(tmp_path: Path, payload: dict) -> tuple[subprocess.CompletedProcess[str], dict, dict]:
    source = tmp_path / "corpus_inventory.json"
    output = tmp_path / "corpus_inventory_deduplicated.json"
    duplicates = tmp_path / "duplicate_sources.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory-json",
            str(source),
            "--output-json",
            str(output),
            "--duplicate-report",
            str(duplicates),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    output_payload = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    duplicate_payload = json.loads(duplicates.read_text(encoding="utf-8")) if duplicates.exists() else {}
    return result, output_payload, duplicate_payload


def test_cli_deduplicates_physical_sha_and_writes_evidence(tmp_path: Path) -> None:
    result, output, duplicates = run_cli(
        tmp_path,
        {
            "summary": {"file_count": 3},
            "files": [
                {"path": "z.parquet", "sha256": "same", "rows": 20},
                {"path": "a.parquet", "sha256": "same", "rows": 20},
                {"path": "b.parquet", "sha256": "different", "rows": 30},
            ],
        },
    )

    assert result.returncode == 0, result.stderr
    assert [item["path"] for item in output["files"]] == ["a.parquet", "b.parquet"]
    assert output["source_file_count_before_deduplication"] == 3
    assert output["source_file_count_after_deduplication"] == 2
    assert output["duplicate_source_count"] == 1
    assert len(output["semantic_sha256"]) == 64
    assert duplicates["duplicates"] == [
        {
            "path": "z.parquet",
            "duplicate_of": "a.parquet",
            "identity": "same",
        }
    ]
    assert len(duplicates["semantic_sha256"]) == 64


def test_cli_keeps_distinct_path_identities_when_sha_is_absent(tmp_path: Path) -> None:
    result, output, duplicates = run_cli(
        tmp_path,
        {"files": [{"path": "a.parquet"}, {"path": "b.parquet"}]},
    )

    assert result.returncode == 0, result.stderr
    assert [item["path"] for item in output["files"]] == ["a.parquet", "b.parquet"]
    assert output["duplicate_source_count"] == 0
    assert duplicates["duplicates"] == []


def test_cli_fails_closed_when_inventory_files_are_missing(tmp_path: Path) -> None:
    result, output, duplicates = run_cli(tmp_path, {"summary": {"file_count": 0}})

    assert result.returncode != 0
    assert "Inventory does not contain files[]" in result.stderr
    assert output == {}
    assert duplicates == {}

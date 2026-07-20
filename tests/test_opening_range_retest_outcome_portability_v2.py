from __future__ import annotations

import json
from pathlib import Path

from research.opening_range_retest_outcomes_v2.contract import canonical_json_bytes, sha256_bytes, sha256_file
from research.opening_range_retest_outcomes_v2.engine import verify_inputs, verify_sidecar_file
from research.opening_range_retest_outcomes_v2.oracle import input_sidecar_failures, verify_sidecar
from scripts.generate_opening_range_retest_outcomes_v2 import _projection_hash

NON_PORTABLE_SIDECAR_PATHS = (
    "/home/runner/work/repo/file.json",
    "/opt/build/file.json",
    "/var/tmp/file.json",
    "/root/project/file.json",
    "/mnt/data/file.json",
    "/Users/example/repo/file.json",
    "/tmp/file.json",
    "/private/tmp/file.json",
    "C:\\repo\\file.json",
    "D:/repo/file.json",
    "\\\\server\\share\\file.json",
    "folder/file.json",
    "folder\\file.json",
)

PORTABLE_NON_PATH_VALUES = (
    "https://github.com/example/repo",
    "2026-07-20T09:12:01Z",
    "BUY_CALL",
    "(terminal_close - entry_open) / entry_open",
    "artifact.json",
)


def _write_artifact(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    digest = sha256_file(path)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")


def _write_input_bundle(root: Path) -> None:
    _write_artifact(
        root / "opening_range_retest_causal_replay_source_manifest_v2.json",
        {
            "record_count": 1512,
            "source_manifest_semantic_hash": "243efbbda2dfbe90817408e50a54c5377f45dbb86db460918edb334fc57d3039",
        },
    )
    _write_artifact(
        root / "opening_range_retest_causal_replay_candidate_ledger_v2.json",
        {
            "candidate_count": 2215,
            "candidate_core_semantic_hash": "8f28637e86095884b76ff931bf4f8b1606301895a226f7839949152c630e189a",
            "candidate_provenance_semantic_hash": "b198ebab71cdc4b097360fb2280f2da6ac2ad1595c0da917dbd5a0b7a2dbba48",
        },
    )
    _write_artifact(
        root / "opening_range_retest_causal_replay_summary_v2.json",
        {"decision": "ORB_PHASE1_V2_RECERTIFIED"},
    )
    _write_artifact(
        root / "opening_range_retest_phase1_v2_reconciliation.json",
        {
            "decision": "UNAFFECTED_SUBSET_RECONCILED",
            "v1_unaffected_candidate_count": 2192,
            "v2_unaffected_candidate_count": 2192,
        },
    )
    _write_artifact(
        root / "opening_range_retest_phase1_v2_certification.md",
        "- decision: ORB_PHASE1_V2_RECERTIFIED\n",
    )


def test_engine_and_oracle_sidecar_identity_are_portable_and_equal(tmp_path: Path) -> None:
    artifact = tmp_path / "nested" / "artifact.json"
    _write_artifact(artifact, {"a": 1})

    engine_sidecar = verify_sidecar_file(artifact)
    oracle_sidecar = verify_sidecar(artifact)

    assert engine_sidecar == oracle_sidecar
    assert engine_sidecar["path"] == "artifact.json"
    assert "/" not in str(engine_sidecar["path"])
    assert "\\" not in str(engine_sidecar["path"])


def test_verify_inputs_sidecars_are_root_independent(tmp_path: Path) -> None:
    root_a = tmp_path / "a" / "artifact-root"
    root_b = tmp_path / "b" / "different-root"
    _write_input_bundle(root_a)
    _write_input_bundle(root_b)

    *_unused_a, sidecars_a = verify_inputs(root_a)
    *_unused_b, sidecars_b = verify_inputs(root_b)

    assert sidecars_a == sidecars_b
    assert {item["path"] for item in sidecars_a.values()} == {
        "opening_range_retest_causal_replay_source_manifest_v2.json",
        "opening_range_retest_causal_replay_candidate_ledger_v2.json",
        "opening_range_retest_causal_replay_summary_v2.json",
        "opening_range_retest_phase1_v2_reconciliation.json",
        "opening_range_retest_phase1_v2_certification.md",
    }


def test_input_sidecar_failures_reject_absolute_paths(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    _write_artifact(artifact, {"a": 1})
    expected = {"artifact": verify_sidecar(artifact)}

    for bad_path in NON_PORTABLE_SIDECAR_PATHS:
        actual = {"artifact": {**expected["artifact"], "path": bad_path}}
        assert input_sidecar_failures(expected, actual) == ["INPUT_SIDECAR_PATH_NOT_PORTABLE:artifact"]


def test_input_sidecar_failures_detect_hash_and_match_flag_drift(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    _write_artifact(artifact, {"a": 1})
    expected = {"artifact": verify_sidecar(artifact)}

    actual = {
        "artifact": {
            **expected["artifact"],
            "artifact_sha256": "0" * 64,
            "sidecar_sha256": "1" * 64,
            "sidecar_match": False,
        }
    }

    assert input_sidecar_failures(expected, actual) == [
        "INPUT_SIDECAR_ARTIFACT_HASH_MISMATCH:artifact",
        "INPUT_SIDECAR_DECLARED_HASH_MISMATCH:artifact",
        "INPUT_SIDECAR_MATCH_FLAG_MISMATCH:artifact",
    ]


def test_projection_hash_keeps_portable_sidecar_evidence_and_rejects_absolute_paths(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    _write_artifact(artifact, {"a": 1})
    sidecar = verify_sidecar(artifact)
    payload = {"ledger": {"input_sidecars": {"artifact": sidecar}}}
    changed = {"ledger": {"input_sidecars": {"artifact": {**sidecar, "artifact_sha256": "0" * 64}}}}

    assert _projection_hash(payload) == sha256_bytes(canonical_json_bytes(payload))
    assert _projection_hash(payload) != _projection_hash(changed)

    absolute = {"ledger": {"input_sidecars": {"artifact": {**sidecar, "path": "/tmp/artifact.json"}}}}
    try:
        _projection_hash(absolute)
    except RuntimeError as exc:
        assert str(exc) == "SEMANTIC_PROJECTION_ABSOLUTE_PATH_LEAK:ledger.input_sidecars.artifact.path"
    else:
        raise AssertionError("expected projection absolute-path rejection")


def test_projection_hash_rejects_generic_absolute_paths() -> None:
    for bad_path in NON_PORTABLE_SIDECAR_PATHS[:11]:
        payload = {"metadata": {"unexpected_location": bad_path}}
        try:
            _projection_hash(payload)
        except RuntimeError as exc:
            assert str(exc) == "SEMANTIC_PROJECTION_ABSOLUTE_PATH_LEAK:metadata.unexpected_location"
        else:
            raise AssertionError(f"expected projection absolute-path rejection for {bad_path!r}")


def test_projection_hash_accepts_non_path_controls() -> None:
    for value in PORTABLE_NON_PATH_VALUES:
        payload = {"metadata": {"value": value}}
        assert _projection_hash(payload) == sha256_bytes(canonical_json_bytes(payload))

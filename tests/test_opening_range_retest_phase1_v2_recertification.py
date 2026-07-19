from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import copy

import pandas as pd

from research.opening_range_retest_v2 import recertification as v2
from research.opening_range_retest_v2.candidate_oracle import audit_candidate_ledger_standalone
from research.opening_range_retest_v2.source_oracle import audit_source_manifest_file_backed


@dataclass(frozen=True)
class _Emission:
    symbol: str
    session_date: str
    direction: str = "BUY_CALL"
    proposal_ready_at_iso: str = "2026-07-06T10:00:00+05:30"
    setup_id: str = "setup"
    history_hash: str = "history"
    raw_score: float = 1.25

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "session_date": self.session_date,
            "direction": self.direction,
            "proposal_ready_at_iso": self.proposal_ready_at_iso,
            "setup_id": self.setup_id,
            "history_hash": self.history_hash,
            "raw_score": self.raw_score,
            "semantic_payload": {
                "strategy_id": "opening_range_retest_v1",
                "symbol": self.symbol,
                "direction": self.direction,
                "status": "CANDIDATE",
                "raw_score": self.raw_score,
                "entry_trigger": "entry",
                "invalid_if": "invalid",
                "rank_reason": "reason",
                "proposal_ready_at_iso": self.proposal_ready_at_iso,
                "setup_id": self.setup_id,
                "history_hash": self.history_hash,
            },
        }


@dataclass(frozen=True)
class _Run:
    source_manifest: dict[str, object]
    emissions: tuple[_Emission, ...]
    summary: dict[str, object]


def _record(symbol: str = "NIFTY", session_date: str = "2026-07-06", logical_path: str | None = None) -> dict[str, object]:
    logical = logical_path or f"runtime/upstox_candidate_replay/20260706/underlying/{symbol}_20260706.parquet"
    return {
        "absolute_path": f"/tmp/repo/{logical}",
        "logical_path": logical,
        "symbol": symbol,
        "session_date": session_date,
        "source_root": "/tmp/repo/runtime/upstox_candidate_replay",
        "sha256": "a" * 64 if symbol == "NIFTY" else "b" * 64,
        "row_count": 375,
        "byte_size": 123,
        "projected_columns": ["timestamp", "symbol", "open", "high", "low", "close", "volume"],
        "selected_via": "inventory_verified_repo_relative",
    }


def _run() -> _Run:
    return _Run(
        source_manifest={"records": [_record()]},
        emissions=(_Emission(symbol="NIFTY", session_date="2026-07-06"),),
        summary={
            "candidate_counts_by_symbol": {"NIFTY": 1},
            "candidate_counts_by_direction": {"BUY_CALL": 1},
            "candidate_counts_by_session": {"2026-07-06": 1},
        },
    )


def _source_frame(symbol: str = "NIFTY", session_date: str = "2026-07-06") -> pd.DataFrame:
    timestamps = pd.date_range(f"{session_date} 09:15", periods=375, freq="min")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": [symbol] * len(timestamps),
            "open": [100.0] * len(timestamps),
            "high": [101.0] * len(timestamps),
            "low": [99.0] * len(timestamps),
            "close": [100.5] * len(timestamps),
            "volume": [1000] * len(timestamps),
        }
    )


def _write_source_file(project_root: Path, symbol: str = "NIFTY", session_date: str = "2026-07-06") -> tuple[Path, str]:
    yyyymmdd = session_date.replace("-", "")
    path = project_root / "runtime" / "upstox_candidate_replay" / yyyymmdd / "underlying" / f"{symbol}_{yyyymmdd}.parquet"
    path.parent.mkdir(parents=True)
    _source_frame(symbol=symbol, session_date=session_date).to_parquet(path, index=False)
    return path, v2.sha256_file(path)


def _file_backed_manifest(project_root: Path) -> dict[str, object]:
    path, digest = _write_source_file(project_root)
    logical = str(path.relative_to(project_root))
    run = _Run(
        source_manifest={
            "records": [
                {
                    **_record(logical_path=logical),
                    "absolute_path": str(path),
                    "sha256": digest,
                    "byte_size": path.stat().st_size,
                }
            ]
        },
        emissions=(_Emission(symbol="NIFTY", session_date="2026-07-06"),),
        summary={},
    )
    return v2.build_source_manifest_v2(run, base_main_sha="base", execution_commit_sha="head")


def test_source_manifest_v2_uses_portable_identity_not_absolute_path() -> None:
    manifest = v2.build_source_manifest_v2(_run(), base_main_sha="base", execution_commit_sha="head")
    record = manifest["records"][0]
    assert manifest["source_manifest_version"] == "v2"
    assert record["logical_path"].startswith("runtime/upstox_candidate_replay/")
    assert record["actual_sha256"] == "a" * 64
    assert "diagnostic_absolute_path" in record
    semantic_payload = v2.source_semantic_payload(manifest)
    assert "diagnostic_absolute_path" not in semantic_payload[0]


def test_candidate_ledger_has_separate_core_and_provenance_hashes() -> None:
    manifest = v2.build_source_manifest_v2(_run(), base_main_sha="base", execution_commit_sha="head")
    ledger = v2.build_candidate_ledger_v2(_run(), manifest)
    assert ledger["candidate_count"] == 1
    assert ledger["candidate_core_semantic_hash"] != ledger["candidate_provenance_semantic_hash"]
    provenance = ledger["records"][0]["source_provenance"]
    assert provenance["source_manifest_version"] == "v2"
    assert provenance["source_logical_path"].startswith("runtime/upstox_candidate_replay/")
    assert "absolute_path" not in str(provenance)


def test_source_oracle_rejects_duplicate_session_symbol() -> None:
    run = _Run(
        source_manifest={"records": [_record(), _record(logical_path="runtime/upstox_candidate_replay/20260706/underlying/NIFTY_DUP_20260706.parquet")]},
        emissions=(),
        summary={},
    )
    manifest = v2.build_source_manifest_v2(run, base_main_sha="base", execution_commit_sha="head")
    audit = v2.audit_source_manifest(manifest)
    assert audit["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED"
    assert "DUPLICATE_SESSION_SYMBOL_SOURCE" in audit["failures"]


def test_candidate_oracle_rejects_missing_source_reference() -> None:
    manifest = v2.build_source_manifest_v2(_run(), base_main_sha="base", execution_commit_sha="head")
    ledger = v2.build_candidate_ledger_v2(_run(), manifest)
    ledger["records"][0]["source_provenance"]["source_record_id"] = "missing"
    audit = v2.audit_candidate_ledger(ledger, manifest)
    assert audit["verdict"] == "ORB_PHASE1_V2_CANDIDATE_LEDGER_NOT_CERTIFIED"
    assert "CANDIDATE_SOURCE_RECORD_ABSENT" in audit["failures"]


def test_json_sidecar_uses_canonical_payload(tmp_path: Path) -> None:
    payload = {"b": 2, "a": 1}
    path = tmp_path / "artifact.json"
    digest = v2.write_json_with_sidecar(payload, path)
    assert path.read_text(encoding="utf-8") == '{"a":1,"b":2}\n'
    assert path.with_suffix(path.suffix + ".sha256").read_text(encoding="utf-8").startswith(digest)


def test_candidate_core_subset_hash_uses_v2_candidate_core_payload() -> None:
    manifest = v2.build_source_manifest_v2(_run(), base_main_sha="base", execution_commit_sha="head")
    ledger = v2.build_candidate_ledger_v2(_run(), manifest)
    digest = v2._candidate_core_hash(ledger["records"])
    expected = v2.sha256_bytes(v2.canonical_json_bytes([ledger["records"][0]["candidate_core"]]))
    assert digest == expected
    assert digest != v2._legacy_v1_unaffected_hash([ledger["records"][0]["candidate_core"]])


def test_file_backed_source_oracle_accepts_contained_exact_file(tmp_path: Path) -> None:
    manifest = _file_backed_manifest(tmp_path)
    audit = audit_source_manifest_file_backed(manifest, source_project_root=tmp_path)
    assert audit["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_CERTIFIED"
    assert audit["source_files_byte_probed"] == 1
    assert audit["source_files_resolved"] == 1
    assert audit["source_files_parquet_read"] == 1
    assert audit["source_sha_matches"] == 1
    assert audit["source_record_id_matches"] == 1


def test_file_backed_source_oracle_rejects_missing_file(tmp_path: Path) -> None:
    (tmp_path / "runtime" / "upstox_candidate_replay").mkdir(parents=True)
    manifest = v2.build_source_manifest_v2(_run(), base_main_sha="base", execution_commit_sha="head")
    audit = audit_source_manifest_file_backed(manifest, source_project_root=tmp_path)
    assert audit["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED"
    assert "SOURCE_FILE_MISSING" in audit["failures"]


def test_file_backed_source_oracle_rejects_changed_bytes(tmp_path: Path) -> None:
    manifest = _file_backed_manifest(tmp_path)
    record = manifest["records"][0]
    record["actual_sha256"] = "0" * 64
    audit = audit_source_manifest_file_backed(manifest, source_project_root=tmp_path)
    assert audit["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED"
    assert "SOURCE_ACTUAL_SHA_MISMATCH" in audit["failures"]


def test_source_oracle_requires_explicit_authority(tmp_path: Path) -> None:
    manifest = _file_backed_manifest(tmp_path)
    audit = audit_source_manifest_file_backed(manifest, source_project_root=None)
    assert audit["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED"
    assert "SOURCE_AUTHORITY_NOT_SUPPLIED" in audit["failures"]
    assert audit["source_files_byte_probed"] == 0


def test_source_oracle_rejects_missing_authority_root(tmp_path: Path) -> None:
    manifest = v2.build_source_manifest_v2(_run(), base_main_sha="base", execution_commit_sha="head")
    audit = audit_source_manifest_file_backed(manifest, source_project_root=tmp_path / "missing")
    assert audit["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED"
    assert "SOURCE_AUTHORITY_ROOT_MISSING" in audit["failures"]
    assert audit["source_files_byte_probed"] == 0


def test_source_oracle_rejects_file_authority_root(tmp_path: Path) -> None:
    manifest = v2.build_source_manifest_v2(_run(), base_main_sha="base", execution_commit_sha="head")
    root_file = tmp_path / "runtime" / "upstox_candidate_replay"
    root_file.parent.mkdir(parents=True, exist_ok=True)
    root_file.write_text("not a directory", encoding="utf-8")
    audit = audit_source_manifest_file_backed(manifest, source_project_root=tmp_path)
    assert audit["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED"
    assert "SOURCE_AUTHORITY_ROOT_NOT_DIRECTORY" in audit["failures"]
    assert audit["source_files_byte_probed"] == 0


def test_source_oracle_rejects_absolute_traversal_and_wrong_prefix(tmp_path: Path) -> None:
    (tmp_path / "runtime" / "upstox_candidate_replay").mkdir(parents=True)
    for logical_path, failure in [
        ("/tmp/source.parquet", "SOURCE_ABSOLUTE_PATH"),
        ("runtime/upstox_candidate_replay/../source.parquet", "SOURCE_PATH_TRAVERSAL"),
        ("runtime/other/source.parquet", "SOURCE_LOGICAL_PREFIX_INVALID"),
    ]:
        run = _Run(source_manifest={"records": [_record(logical_path=logical_path)]}, emissions=(), summary={})
        manifest = v2.build_source_manifest_v2(run, base_main_sha="base", execution_commit_sha="head")
        audit = audit_source_manifest_file_backed(manifest, source_project_root=tmp_path)
        assert audit["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED"
        assert failure in audit["failures"]
        assert audit["source_files_byte_probed"] == 0


def test_source_oracle_rejects_symlink_component(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    source_root = tmp_path / "runtime" / "upstox_candidate_replay"
    source_root.parent.mkdir(parents=True, exist_ok=True)
    source_root.symlink_to(outside, target_is_directory=True)
    manifest = v2.build_source_manifest_v2(_run(), base_main_sha="base", execution_commit_sha="head")
    audit = audit_source_manifest_file_backed(manifest, source_project_root=tmp_path)
    assert audit["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED"
    assert "SOURCE_SYMLINK_COMPONENT" in audit["failures"]
    assert audit["source_files_byte_probed"] == 0


def test_source_oracle_ignores_diagnostic_absolute_path(tmp_path: Path) -> None:
    manifest = _file_backed_manifest(tmp_path)
    manifest["records"][0]["diagnostic_absolute_path"] = "/tmp/not-authoritative.parquet"
    before = v2.sha256_bytes(v2.canonical_json_bytes(v2.source_semantic_payload(manifest)))
    audit = audit_source_manifest_file_backed(manifest, source_project_root=tmp_path)
    after = v2.sha256_bytes(v2.canonical_json_bytes(v2.source_semantic_payload(manifest)))
    assert audit["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_CERTIFIED"
    assert before == after == manifest["source_manifest_semantic_hash"]


def test_source_oracle_portable_hash_unchanged_across_authorities(tmp_path: Path) -> None:
    manifest_a = _file_backed_manifest(tmp_path / "a")
    manifest_b = copy.deepcopy(manifest_a)
    _write_source_file(tmp_path / "b")
    manifest_b["records"][0]["diagnostic_absolute_path"] = "/different/root/source.parquet"
    audit_a = audit_source_manifest_file_backed(manifest_a, source_project_root=tmp_path / "a")
    audit_b = audit_source_manifest_file_backed(manifest_b, source_project_root=tmp_path / "b")
    assert audit_a["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_CERTIFIED"
    assert audit_b["verdict"] == "ORB_PHASE1_V2_SOURCE_MANIFEST_CERTIFIED"
    assert manifest_a["source_manifest_semantic_hash"] == manifest_b["source_manifest_semantic_hash"]


def test_standalone_candidate_oracle_rejects_candidate_id_drift() -> None:
    manifest = v2.build_source_manifest_v2(_run(), base_main_sha="base", execution_commit_sha="head")
    ledger = v2.build_candidate_ledger_v2(_run(), manifest)
    ledger["records"][0]["candidate_id"] = "0" * 64
    audit = audit_candidate_ledger_standalone(ledger, manifest)
    assert audit["verdict"] == "ORB_PHASE1_V2_CANDIDATE_LEDGER_NOT_CERTIFIED"
    assert "CANDIDATE_ID_MISMATCH" in audit["failures"]


def test_standalone_candidate_oracle_rejects_ordering_drift() -> None:
    first = _Emission(symbol="NIFTY", session_date="2026-07-06", setup_id="b", proposal_ready_at_iso="2026-07-06T10:01:00+05:30")
    second = _Emission(symbol="NIFTY", session_date="2026-07-06", setup_id="a", proposal_ready_at_iso="2026-07-06T10:00:00+05:30")
    run = _Run(source_manifest={"records": [_record()]}, emissions=(first, second), summary={})
    manifest = v2.build_source_manifest_v2(run, base_main_sha="base", execution_commit_sha="head")
    ledger = v2.build_candidate_ledger_v2(run, manifest)
    ledger["records"] = list(reversed(ledger["records"]))
    ledger["candidate_provenance_semantic_hash"] = v2.sha256_bytes(v2.canonical_json_bytes(ledger["records"]))
    audit = audit_candidate_ledger_standalone(ledger, manifest)
    assert audit["verdict"] == "ORB_PHASE1_V2_CANDIDATE_LEDGER_NOT_CERTIFIED"
    assert "CANDIDATE_ORDERING_MISMATCH" in audit["failures"]

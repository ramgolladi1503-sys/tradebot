from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "research" / "hypothesis_factory"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sealer = load("seal_live_observation_bundle_v1", "seal_live_observation_bundle_v1.py")
ingest = load("ingest_live_observation_evidence_v1", "ingest_live_observation_evidence_v1.py")

PRODUCER_SHA = "f0f5b3d3659415ab36662291e91b8f57fd8d1e07"
OBS_DATE = "2026-08-18"


def run(*args: str, cwd: Path) -> str:
    completed = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def init_producer(tmp_path: Path) -> tuple[Path, str]:
    producer = tmp_path / "producer-worktree"
    producer.mkdir()
    run("git", "init", "-q", cwd=producer)
    run("git", "config", "user.email", "test@example.com", cwd=producer)
    run("git", "config", "user.name", "test", cwd=producer)
    (producer / "README.md").write_text("frozen producer\n")
    run("git", "add", "README.md", cwd=producer)
    run("git", "commit", "-q", "-m", "producer", cwd=producer)
    sha = run("git", "rev-parse", "HEAD", cwd=producer)
    return producer, sha


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_h1_csv(path: Path, count: int = 27) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime.fromisoformat(f"{OBS_DATE}T09:15:00+05:30")
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["datetime", "open", "high", "low", "close"], lineterminator="\n")
        writer.writeheader()
        for index in range(count):
            ts = start + timedelta(minutes=5 * index)
            base = 24000.0 + index
            writer.writerow(
                {
                    "datetime": ts.strftime("%Y-%m-%d %H:%M:%S%z"),
                    "open": base,
                    "high": base + 2,
                    "low": base - 2,
                    "close": base + 1,
                }
            )


def make_h1_files(runtime: Path, *, count: int = 27, missing_to_zero: bool = False) -> dict[str, Path]:
    sqlite = runtime / "producer" / "db" / "DEFAULT.sqlite"
    sqlite.parent.mkdir(parents=True, exist_ok=True)
    sqlite.write_bytes(b"immutable sqlite fixture bytes")
    bars = runtime / "eod" / "h1_20260818.csv"
    write_h1_csv(bars, count=count)
    manifest = runtime / "eod" / "h1_20260818_manifest.json"
    payload = {
        "exporter_version": "H1_LIVE_CAPTURE_EXPORTER_V1",
        "source_path": str(sqlite.resolve()),
        "source_sha256": file_sha(sqlite),
        "source_size": sqlite.stat().st_size,
        "source_format": "sqlite",
        "instrument_identity": "NIFTY 50",
        "instrument_token": 256265,
        "timezone": "Asia/Kolkata",
        "bar_interval": "5m",
        "session_filter": "09:15-11:30 IST",
        "coverage_complete": count == 27,
        "complete_bar_count": count,
        "missing_bar_count": 27 - count,
        "missing_bar_policy": "MISSING; no forward-fill, backfill, interpolation, or substitution",
        "h1_replay_input_valid": count == 27,
        "output_csv_sha256": file_sha(bars),
        "source_db_mutated": False,
        "orders_created": 0,
        "broker_writes_created": 0,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }
    if missing_to_zero:
        payload["missing_as_zero"] = True
    manifest.write_text(json.dumps(payload, sort_keys=True) + "\n")
    return {"sqlite": sqlite, "bars": bars, "manifest": manifest}


def specs(files: dict[str, Path]) -> list[str]:
    return [
        f"PRODUCER_SQLITE:LIVE_PROSPECTIVE:PRODUCER_RAW:{files['sqlite'].resolve()}",
        f"H1_BARS_CSV:LIVE_PROSPECTIVE:READ_ONLY_DERIVED:{files['bars'].resolve()}",
        f"H1_EXPORT_MANIFEST:LIVE_PROSPECTIVE:DERIVED_MANIFEST:{files['manifest'].resolve()}",
    ]


def make_bundle(tmp_path: Path, *, count: int = 27, missing_to_zero: bool = False):
    producer, actual_sha = init_producer(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    files = make_h1_files(runtime, count=count, missing_to_zero=missing_to_zero)
    bundle_path = runtime / "eod" / "kernel_bundle.json"
    kernel_root = tmp_path / "kernel-repo"
    kernel_root.mkdir()
    sealer.seal_bundle(
        producer_worktree=producer,
        expected_producer_sha=actual_sha,
        runtime_root=runtime,
        observation_date=OBS_DATE,
        artifact_specs=specs(files),
        output_manifest=bundle_path,
        kernel_repo_root=kernel_root,
    )
    return producer, actual_sha, runtime, files, bundle_path, kernel_root


def test_valid_h1_bundle_is_verified_without_authority_promotion(tmp_path: Path):
    producer, sha, runtime, _, bundle, kernel_root = make_bundle(tmp_path)
    output = runtime / "eod" / "kernel_ingestion.json"
    result = ingest.ingest_bundle(
        bundle_manifest=bundle,
        expected_producer_sha=sha,
        observation_date=OBS_DATE,
        output_record=output,
        kernel_repo_root=kernel_root,
    )
    assert result["status"] == "KERNEL_INGESTION_VERIFIED"
    assert result["h1_validation"]["status"] == "H1_27_BAR_BINDING_VERIFIED"
    assert result["prospective_evidence_created"] is False
    assert result["structural_edge_certified"] is False
    assert result["broker_write_authority"] is False
    assert result["order_authority"] is False
    assert output.is_file()
    assert run("git", "status", "--porcelain", cwd=producer) == ""


def test_sealer_rejects_wrong_producer_sha(tmp_path: Path):
    producer, _ = init_producer(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    files = make_h1_files(runtime)
    with pytest.raises(ValueError, match="PRODUCER_SHA_MISMATCH"):
        sealer.seal_bundle(
            producer_worktree=producer,
            expected_producer_sha="0" * 40,
            runtime_root=runtime,
            observation_date=OBS_DATE,
            artifact_specs=specs(files),
            output_manifest=runtime / "bundle.json",
            kernel_repo_root=tmp_path / "kernel",
        )


def test_sealer_rejects_dirty_producer(tmp_path: Path):
    producer, sha = init_producer(tmp_path)
    (producer / "dirty.txt").write_text("drift")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    files = make_h1_files(runtime)
    with pytest.raises(ValueError, match="PRODUCER_WORKTREE_DIRTY"):
        sealer.seal_bundle(
            producer_worktree=producer,
            expected_producer_sha=sha,
            runtime_root=runtime,
            observation_date=OBS_DATE,
            artifact_specs=specs(files),
            output_manifest=runtime / "bundle.json",
            kernel_repo_root=tmp_path / "kernel",
        )


def test_ingestion_rejects_artifact_tampering(tmp_path: Path):
    _, sha, runtime, files, bundle, kernel_root = make_bundle(tmp_path)
    files["bars"].write_text(files["bars"].read_text() + "tamper\n")
    with pytest.raises(ValueError, match="ARTIFACT_HASH_MISMATCH:H1_BARS_CSV"):
        ingest.ingest_bundle(
            bundle_manifest=bundle,
            expected_producer_sha=sha,
            observation_date=OBS_DATE,
            output_record=runtime / "eod" / "out.json",
            kernel_repo_root=kernel_root,
        )


def test_ingestion_rejects_wrong_observation_date(tmp_path: Path):
    _, sha, runtime, _, bundle, kernel_root = make_bundle(tmp_path)
    with pytest.raises(ValueError, match="BUNDLE_OBSERVATION_DATE_MISMATCH"):
        ingest.ingest_bundle(
            bundle_manifest=bundle,
            expected_producer_sha=sha,
            observation_date="2026-08-19",
            output_record=runtime / "eod" / "out.json",
            kernel_repo_root=kernel_root,
        )


def test_ingestion_rejects_missing_to_zero_metadata(tmp_path: Path):
    _, sha, runtime, _, bundle, kernel_root = make_bundle(tmp_path, missing_to_zero=True)
    with pytest.raises(ValueError, match="MISSING_TO_ZERO_REJECTED"):
        ingest.ingest_bundle(
            bundle_manifest=bundle,
            expected_producer_sha=sha,
            observation_date=OBS_DATE,
            output_record=runtime / "eod" / "out.json",
            kernel_repo_root=kernel_root,
        )


def test_ingestion_rejects_incomplete_h1_grid(tmp_path: Path):
    _, sha, runtime, _, bundle, kernel_root = make_bundle(tmp_path, count=26)
    with pytest.raises(ValueError, match="H1_COVERAGE_NOT_VALID"):
        ingest.ingest_bundle(
            bundle_manifest=bundle,
            expected_producer_sha=sha,
            observation_date=OBS_DATE,
            output_record=runtime / "eod" / "out.json",
            kernel_repo_root=kernel_root,
        )


def test_sealer_rejects_symlink_artifact(tmp_path: Path):
    producer, sha = init_producer(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    files = make_h1_files(runtime)
    link = runtime / "eod" / "linked.csv"
    link.symlink_to(files["bars"])
    bad_specs = specs(files)
    bad_specs[1] = f"H1_BARS_CSV:LIVE_PROSPECTIVE:READ_ONLY_DERIVED:{link.resolve().parent / link.name}"
    with pytest.raises(ValueError, match="REGULAR_FILE_REQUIRED"):
        sealer.seal_bundle(
            producer_worktree=producer,
            expected_producer_sha=sha,
            runtime_root=runtime,
            observation_date=OBS_DATE,
            artifact_specs=bad_specs,
            output_manifest=runtime / "bundle.json",
            kernel_repo_root=tmp_path / "kernel",
        )


def test_sealer_rejects_artifact_outside_runtime(tmp_path: Path):
    producer, sha = init_producer(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    files = make_h1_files(runtime)
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n")
    bad_specs = specs(files) + [f"EXTRA:LIVE_PROSPECTIVE:DERIVED_MANIFEST:{outside.resolve()}"]
    with pytest.raises(ValueError, match="ARTIFACT_OUTSIDE_RUNTIME_ROOT:EXTRA"):
        sealer.seal_bundle(
            producer_worktree=producer,
            expected_producer_sha=sha,
            runtime_root=runtime,
            observation_date=OBS_DATE,
            artifact_specs=bad_specs,
            output_manifest=runtime / "bundle.json",
            kernel_repo_root=tmp_path / "kernel",
        )


def test_cas_cannot_be_promoted_to_live_prospective(tmp_path: Path):
    producer, sha = init_producer(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cas = runtime / "eod" / "cas" / "report.json"
    cas.parent.mkdir(parents=True)
    cas.write_text(json.dumps({"status": "CAPTURE_ONLY"}) + "\n")
    bundle = runtime / "eod" / "bundle.json"
    kernel_root = tmp_path / "kernel"
    kernel_root.mkdir()
    sealer.seal_bundle(
        producer_worktree=producer,
        expected_producer_sha=sha,
        runtime_root=runtime,
        observation_date=OBS_DATE,
        artifact_specs=[f"CAS_REPORT:LIVE_PROSPECTIVE:READ_ONLY_DERIVED:{cas.resolve()}"],
        output_manifest=bundle,
        kernel_repo_root=kernel_root,
    )
    with pytest.raises(ValueError, match="CAS_LIVE_PROMOTION_REJECTED"):
        ingest.ingest_bundle(
            bundle_manifest=bundle,
            expected_producer_sha=sha,
            observation_date=OBS_DATE,
            output_record=runtime / "eod" / "out.json",
            kernel_repo_root=kernel_root,
        )


def test_replay_metadata_cannot_be_promoted(tmp_path: Path):
    producer, sha = init_producer(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    report = runtime / "eod" / "cas" / "report.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"offline_replay": True}) + "\n")
    bundle = runtime / "eod" / "bundle.json"
    kernel_root = tmp_path / "kernel"
    kernel_root.mkdir()
    sealer.seal_bundle(
        producer_worktree=producer,
        expected_producer_sha=sha,
        runtime_root=runtime,
        observation_date=OBS_DATE,
        artifact_specs=[f"CAS_REPORT:CAPTURE_THEN_OFFLINE:READ_ONLY_DERIVED:{report.resolve()}"],
        output_manifest=bundle,
        kernel_repo_root=kernel_root,
    )
    with pytest.raises(ValueError, match="NON_PROSPECTIVE_SOURCE_REJECTED"):
        ingest.ingest_bundle(
            bundle_manifest=bundle,
            expected_producer_sha=sha,
            observation_date=OBS_DATE,
            output_record=runtime / "eod" / "out.json",
            kernel_repo_root=kernel_root,
        )


def test_output_cannot_write_into_producer_or_kernel_repo(tmp_path: Path):
    producer, sha, runtime, _, bundle, kernel_root = make_bundle(tmp_path)
    with pytest.raises(ValueError, match="OUTPUT_MUST_BE_EXTERNAL_TO_REPOSITORIES"):
        ingest.ingest_bundle(
            bundle_manifest=bundle,
            expected_producer_sha=sha,
            observation_date=OBS_DATE,
            output_record=producer / "bad.json",
            kernel_repo_root=kernel_root,
        )


def test_source_contains_no_broker_or_websocket_ownership_imports():
    source = (SCRIPTS / "ingest_live_observation_evidence_v1.py").read_text().lower()
    sealer_source = (SCRIPTS / "seal_live_observation_bundle_v1.py").read_text().lower()
    for forbidden in ("kiteconnect", "kiteconnect.", "websocketapp", "place_order(", "modify_order(", "cancel_order("):
        assert forbidden not in source
        assert forbidden not in sealer_source

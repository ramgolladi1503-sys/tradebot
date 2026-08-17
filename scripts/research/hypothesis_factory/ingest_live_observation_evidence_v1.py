#!/usr/bin/env python3
"""Fail-closed post-close ingestion for sealed TradeBot observation bundles.

This adapter re-verifies the frozen producer authority and every artifact byte.
It preserves missing values, rejects replay/synthetic/historical promotion, and
writes only an external ingestion record. It never grants trading authority.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "tradebot-live-observation-bundle-v1"
OUTPUT_SCHEMA = "tradebot-live-observation-kernel-ingestion-v1"
KERNEL_BASE_AUTHORITY_SHA = "46dd4f7df9b63486eb633a12baf25412cd4f761d"
ALLOWED_STATES = {"LIVE_PROSPECTIVE", "CAPTURE_THEN_OFFLINE"}
REJECTED_SOURCE_WORDS = {"historical", "replay", "synthetic", "fallback"}


def strict_json_load(path: Path) -> Any:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"JSON_DUPLICATE_KEY:{key}")
            out[key] = value
        return out

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_sha(value: Any, *, field: str) -> str:
    text = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", text):
        raise ValueError(f"{field}_EXACT_SHA_REQUIRED")
    return text


def exact_sha256(value: Any, *, field: str) -> str:
    text = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError(f"{field}_SHA256_REQUIRED")
    return text


def regular_file(path: Path, *, code: str) -> Path:
    absolute = path.expanduser().absolute()
    if absolute.is_symlink() or not absolute.is_file():
        raise ValueError(f"{code}_REGULAR_FILE_REQUIRED:{absolute}")
    return absolute.resolve()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def git_output(worktree: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ValueError(f"PRODUCER_GIT_CHECK_FAILED:{' '.join(args)}")
    return completed.stdout.strip()


def verify_live_producer(bundle: Mapping[str, Any], expected_sha: str, expected_date: str) -> tuple[Path, Path]:
    if bundle.get("schema") != SCHEMA:
        raise ValueError("BUNDLE_SCHEMA_INVALID")
    try:
        observed_date = date.fromisoformat(str(bundle.get("observation_date") or "")).isoformat()
    except ValueError as exc:
        raise ValueError("BUNDLE_OBSERVATION_DATE_INVALID") from exc
    if observed_date != expected_date:
        raise ValueError("BUNDLE_OBSERVATION_DATE_MISMATCH")
    if bundle.get("kernel_base_authority_sha") != KERNEL_BASE_AUTHORITY_SHA:
        raise ValueError("KERNEL_BASE_AUTHORITY_MISMATCH")

    producer = bundle.get("producer")
    if not isinstance(producer, Mapping):
        raise ValueError("PRODUCER_AUTHORITY_MISSING")
    declared = exact_sha(producer.get("git_sha"), field="BUNDLE_PRODUCER")
    expected = exact_sha(expected_sha, field="EXPECTED_PRODUCER")
    if declared != expected:
        raise ValueError("BUNDLE_PRODUCER_SHA_MISMATCH")
    if producer.get("git_clean") is not True:
        raise ValueError("BUNDLE_PRODUCER_NOT_CLEAN")
    if producer.get("source_authentication") != "GIT_WORKTREE_EXACT_SHA_AND_CLEAN":
        raise ValueError("PRODUCER_AUTHENTICATION_INVALID")

    worktree = Path(str(producer.get("worktree") or "")).expanduser().resolve()
    if not worktree.is_dir():
        raise ValueError("PRODUCER_WORKTREE_MISSING")
    actual = exact_sha(git_output(worktree, "rev-parse", "HEAD"), field="ACTUAL_PRODUCER")
    if actual != expected:
        raise ValueError("PRODUCER_SHA_DRIFT")
    if git_output(worktree, "status", "--porcelain"):
        raise ValueError("PRODUCER_WORKTREE_DIRTY")

    runtime = Path(str(bundle.get("runtime_root") or "")).expanduser().resolve()
    if not runtime.is_dir():
        raise ValueError("RUNTIME_ROOT_MISSING")
    if is_within(runtime, worktree):
        raise ValueError("RUNTIME_ROOT_INSIDE_PRODUCER_REPO")
    return worktree, runtime


def reject_promotional_json(payload: Any, *, path: str = "$") -> None:
    """Reject explicit provenance promotion or missing->zero markers.

    This intentionally checks semantic keys rather than arbitrary prose so a
    report may discuss replay/historical controls without being rejected.
    """
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            lower = str(key).lower()
            child = f"{path}.{key}"
            if lower in {"missing_as_zero", "missing_to_zero", "missing_values_zero_filled", "zero_fill_missing"} and value is True:
                raise ValueError(f"MISSING_TO_ZERO_REJECTED:{child}")
            if lower in {"replay", "synthetic", "fallback", "historical", "offline_replay"} and value is True:
                raise ValueError(f"NON_PROSPECTIVE_SOURCE_REJECTED:{child}")
            if lower in {"source_class", "source_type", "evidence_state", "provenance"} and isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in REJECTED_SOURCE_WORDS or any(word in normalized for word in ("historical_replay", "synthetic_replay")):
                    raise ValueError(f"NON_PROSPECTIVE_SOURCE_REJECTED:{child}:{value}")
            reject_promotional_json(value, path=child)
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            reject_promotional_json(value, path=f"{path}[{index}]")


def verify_artifacts(bundle: Mapping[str, Any], runtime_root: Path) -> dict[str, dict[str, Any]]:
    rows = bundle.get("artifacts")
    if not isinstance(rows, list) or not rows:
        raise ValueError("BUNDLE_ARTIFACTS_REQUIRED")
    verified: dict[str, dict[str, Any]] = {}
    seen_paths: set[str] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError("ARTIFACT_DESCRIPTOR_INVALID")
        kind = str(raw.get("evidence_kind") or "")
        if not re.fullmatch(r"[A-Z0-9_]+", kind) or kind in verified:
            raise ValueError(f"ARTIFACT_KIND_INVALID_OR_DUPLICATE:{kind}")
        state = str(raw.get("state") or "")
        if state not in ALLOWED_STATES:
            raise ValueError(f"ARTIFACT_STATE_REJECTED:{kind}:{state}")
        path = regular_file(Path(str(raw.get("path") or "")), code=f"ARTIFACT_{kind}")
        if not is_within(path, runtime_root):
            raise ValueError(f"ARTIFACT_OUTSIDE_RUNTIME_ROOT:{kind}")
        if str(path) in seen_paths:
            raise ValueError(f"ARTIFACT_PATH_REUSED:{path}")
        seen_paths.add(str(path))
        expected_hash = exact_sha256(raw.get("sha256"), field=f"ARTIFACT_{kind}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise ValueError(f"ARTIFACT_HASH_MISMATCH:{kind}")
        try:
            declared_size = int(raw.get("size_bytes"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"ARTIFACT_SIZE_INVALID:{kind}") from exc
        if declared_size != path.stat().st_size:
            raise ValueError(f"ARTIFACT_SIZE_MISMATCH:{kind}")
        if path.suffix.lower() == ".json":
            reject_promotional_json(strict_json_load(path))
        verified[kind] = {
            "path": str(path),
            "sha256": actual_hash,
            "size_bytes": declared_size,
            "state": state,
            "role": raw.get("role"),
        }
    return verified


def false_authority(value: Any) -> bool:
    return value is False or value == 0


def validate_h1(verified: Mapping[str, Mapping[str, Any]], observation_date: str) -> dict[str, Any] | None:
    present = {"H1_BARS_CSV", "H1_EXPORT_MANIFEST", "PRODUCER_SQLITE"} & set(verified)
    if not present:
        return None
    required = {"H1_BARS_CSV", "H1_EXPORT_MANIFEST", "PRODUCER_SQLITE"}
    missing = required - set(verified)
    if missing:
        raise ValueError(f"H1_REQUIRED_ARTIFACTS_MISSING:{sorted(missing)}")
    if any(verified[k]["state"] != "LIVE_PROSPECTIVE" for k in required):
        raise ValueError("H1_STATE_MUST_BE_LIVE_PROSPECTIVE")

    csv_path = Path(str(verified["H1_BARS_CSV"]["path"]))
    manifest_path = Path(str(verified["H1_EXPORT_MANIFEST"]["path"]))
    sqlite_path = Path(str(verified["PRODUCER_SQLITE"]["path"]))
    manifest = strict_json_load(manifest_path)
    if not isinstance(manifest, Mapping):
        raise ValueError("H1_MANIFEST_INVALID")
    if exact_sha256(manifest.get("output_csv_sha256"), field="H1_OUTPUT") != verified["H1_BARS_CSV"]["sha256"]:
        raise ValueError("H1_OUTPUT_BINDING_MISMATCH")
    if exact_sha256(manifest.get("source_sha256"), field="H1_SOURCE") != verified["PRODUCER_SQLITE"]["sha256"]:
        raise ValueError("H1_SOURCE_HASH_BINDING_MISMATCH")
    if Path(str(manifest.get("source_path") or "")).expanduser().resolve() != sqlite_path:
        raise ValueError("H1_SOURCE_PATH_BINDING_MISMATCH")
    if str(manifest.get("source_format")) != "sqlite":
        raise ValueError("H1_SOURCE_FORMAT_INVALID")
    if manifest.get("h1_replay_input_valid") is not True or manifest.get("coverage_complete") is not True:
        raise ValueError("H1_COVERAGE_NOT_VALID")
    if int(manifest.get("complete_bar_count", -1)) != 27 or int(manifest.get("missing_bar_count", -1)) != 0:
        raise ValueError("H1_27_BAR_CONTRACT_FAILED")
    if manifest.get("missing_bar_policy") != "MISSING; no forward-fill, backfill, interpolation, or substitution":
        raise ValueError("H1_MISSING_POLICY_INVALID")
    if manifest.get("source_db_mutated") is not False:
        raise ValueError("H1_SOURCE_MUTATION_FLAG_INVALID")
    for key in ("broker_write_authority", "order_authority", "paper_authorized", "live_authorized"):
        if manifest.get(key) is not False:
            raise ValueError(f"H1_AUTHORITY_FLAG_INVALID:{key}")
    for key in ("orders_created", "broker_writes_created"):
        if manifest.get(key) != 0:
            raise ValueError(f"H1_SIDE_EFFECT_COUNT_NONZERO:{key}")

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 27:
        raise ValueError("H1_CSV_ROW_COUNT_INVALID")
    expected_start = datetime.fromisoformat(f"{observation_date}T09:15:00+05:30")
    expected_times = [expected_start + timedelta(minutes=5 * index) for index in range(27)]
    for index, row in enumerate(rows):
        try:
            ts = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S%z")
        except (KeyError, ValueError) as exc:
            raise ValueError(f"H1_CSV_TIMESTAMP_INVALID:{index}") from exc
        if ts != expected_times[index]:
            raise ValueError(f"H1_CSV_TIME_GRID_INVALID:{index}")
        for field in ("open", "high", "low", "close"):
            try:
                value = float(row[field])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"H1_CSV_OHLC_INVALID:{index}:{field}") from exc
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"H1_CSV_OHLC_INVALID:{index}:{field}")
        if float(row["high"]) < max(float(row["open"]), float(row["close"]), float(row["low"])):
            raise ValueError(f"H1_CSV_OHLC_RELATION_INVALID:{index}")
        if float(row["low"]) > min(float(row["open"]), float(row["close"]), float(row["high"])):
            raise ValueError(f"H1_CSV_OHLC_RELATION_INVALID:{index}")
    return {
        "status": "H1_27_BAR_BINDING_VERIFIED",
        "bar_count": 27,
        "observation_date": observation_date,
        "source_sha256": verified["PRODUCER_SQLITE"]["sha256"],
        "bars_sha256": verified["H1_BARS_CSV"]["sha256"],
    }


def validate_cas_states(verified: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
    cas = {kind: row for kind, row in verified.items() if kind.startswith("CAS_")}
    if not cas:
        return None
    wrong = sorted(kind for kind, row in cas.items() if row["state"] != "CAPTURE_THEN_OFFLINE")
    if wrong:
        raise ValueError(f"CAS_LIVE_PROMOTION_REJECTED:{wrong}")
    return {
        "status": "CAS_CAPTURE_THEN_OFFLINE_ONLY",
        "artifact_kinds": sorted(cas),
        "directional_edge_validated": False,
    }


def ingest_bundle(
    *,
    bundle_manifest: Path,
    expected_producer_sha: str,
    observation_date: str,
    output_record: Path,
    kernel_repo_root: Path | None = None,
) -> dict[str, Any]:
    try:
        expected_date = date.fromisoformat(observation_date).isoformat()
    except ValueError as exc:
        raise ValueError("EXPECTED_OBSERVATION_DATE_INVALID") from exc
    manifest_path = regular_file(bundle_manifest, code="BUNDLE_MANIFEST")
    bundle = strict_json_load(manifest_path)
    if not isinstance(bundle, Mapping):
        raise ValueError("BUNDLE_JSON_OBJECT_REQUIRED")
    producer_worktree, runtime_root = verify_live_producer(bundle, expected_producer_sha, expected_date)

    for key in ("broker_write_authority", "order_authority", "paper_authorized", "live_authorized", "structural_edge_certified"):
        if bundle.get(key) is not False:
            raise ValueError(f"BUNDLE_AUTHORITY_FLAG_INVALID:{key}")
    if bundle.get("missing_value_policy") != "PRESERVE_MISSING; NEVER_COERCE_TO_ZERO":
        raise ValueError("BUNDLE_MISSING_POLICY_INVALID")
    if bundle.get("bundle_state") != "CAPTURED_NOT_CERTIFIED":
        raise ValueError("BUNDLE_STATE_INVALID")

    verified = verify_artifacts(bundle, runtime_root)
    h1 = validate_h1(verified, expected_date)
    cas = validate_cas_states(verified)

    output = output_record.expanduser().absolute()
    kernel_root = (kernel_repo_root or Path(__file__).resolve().parents[3]).resolve()
    if is_within(output, producer_worktree) or is_within(output, kernel_root):
        raise ValueError("OUTPUT_MUST_BE_EXTERNAL_TO_REPOSITORIES")
    if not is_within(output, runtime_root):
        raise ValueError("OUTPUT_MUST_BE_INSIDE_EXTERNAL_RUNTIME_ROOT")

    result = {
        "schema": OUTPUT_SCHEMA,
        "status": "KERNEL_INGESTION_VERIFIED",
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "observation_date": expected_date,
        "producer_sha": exact_sha(expected_producer_sha, field="EXPECTED_PRODUCER"),
        "kernel_base_authority_sha": KERNEL_BASE_AUTHORITY_SHA,
        "bundle_manifest_path": str(manifest_path),
        "bundle_manifest_sha256": sha256_file(manifest_path),
        "artifacts": verified,
        "h1_validation": h1,
        "cas_validation": cas,
        "prospective_evidence_created": False,
        "historical_promoted_to_prospective": False,
        "missing_values_coerced_to_zero": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "structural_edge_certified": False,
        "interpretation": "PASS verifies post-close provenance bindings and artifact integrity only; downstream prospective evaluation remains separate.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("OUTPUT_RECORD_ALREADY_EXISTS") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-manifest", required=True)
    parser.add_argument("--expected-producer-sha", required=True)
    parser.add_argument("--observation-date", required=True)
    parser.add_argument("--output-record", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = ingest_bundle(
        bundle_manifest=Path(args.bundle_manifest),
        expected_producer_sha=args.expected_producer_sha,
        observation_date=args.observation_date,
        output_record=Path(args.output_record),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

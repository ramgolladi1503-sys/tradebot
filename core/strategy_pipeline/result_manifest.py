from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from core.strategy_pipeline.pipeline_models import (
    EngineMetrics,
    EngineResult,
    EngineType,
    PipelineState,
)

SCHEMA_VERSION = 1


class ResultManifestError(ValueError):
    """Raised when an engine result manifest is missing, malformed, or forged."""


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_payload(result: EngineResult) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "engine": result.engine.value,
        "state": result.state.value,
        "run_id": result.run_id,
        "strategy_id": result.strategy_id,
        "artifacts_generated": list(result.artifacts_generated),
        "input_hashes": dict(result.input_hashes),
        "output_hashes": dict(result.output_hashes),
        "errors": list(result.errors),
        "blockers": list(result.blockers),
        "limitations": list(result.limitations),
        "command": list(result.command),
        "exit_code": result.exit_code,
        "verdict": result.verdict,
        "cached": result.cached,
        "verified": result.verified,
        "created_timestamp": result.created_timestamp
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "metrics": asdict(result.metrics),
    }
    payload["manifest_sha256"] = sha256_payload(payload)
    return payload


def write_engine_result_manifest(path: str | Path, result: EngineResult) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _manifest_payload(result)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(target)
    return target


def load_engine_result_manifest(path: str | Path) -> EngineResult:
    source = Path(path)
    if not source.is_file():
        raise ResultManifestError(f"result_manifest_missing:{source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResultManifestError(f"result_manifest_unreadable:{source}:{exc}") from exc
    if not isinstance(payload, dict):
        raise ResultManifestError("result_manifest_must_be_object")

    expected = payload.get("manifest_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    if not isinstance(expected, str) or expected != sha256_payload(unsigned):
        raise ResultManifestError("result_manifest_hash_mismatch")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ResultManifestError("result_manifest_schema_unsupported")

    try:
        metrics = EngineMetrics(**dict(payload.get("metrics") or {}))
        result = EngineResult(
            engine=EngineType(payload["engine"]),
            state=PipelineState(payload["state"]),
            run_id=payload.get("run_id"),
            strategy_id=payload.get("strategy_id"),
            artifacts_generated=list(payload.get("artifacts_generated") or []),
            input_hashes=dict(payload.get("input_hashes") or {}),
            output_hashes=dict(payload.get("output_hashes") or {}),
            errors=list(payload.get("errors") or []),
            blockers=list(payload.get("blockers") or []),
            limitations=list(payload.get("limitations") or []),
            command=list(payload.get("command") or []),
            exit_code=payload.get("exit_code"),
            verdict=payload.get("verdict"),
            manifest_path=str(source),
            cached=bool(payload.get("cached", False)),
            verified=bool(payload.get("verified", False)),
            created_timestamp=payload.get("created_timestamp"),
            metrics=metrics,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ResultManifestError(f"result_manifest_invalid:{exc}") from exc
    return result

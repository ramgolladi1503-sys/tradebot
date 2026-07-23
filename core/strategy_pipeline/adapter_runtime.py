from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from core.strategy_pipeline.pipeline_models import (
    EngineMetrics,
    EngineResult,
    EngineType,
    PipelineState,
)
from core.strategy_pipeline.result_manifest import sha256_file, write_engine_result_manifest


class AdapterRuntimeError(ValueError):
    """Raised when a pipeline adapter environment is missing or forged."""


@dataclass(frozen=True)
class PipelineAdapterRuntime:
    repo_root: Path
    engine: EngineType
    run_id: str
    strategy_id: str
    result_manifest: Path
    input_hashes: dict[str, str]

    _ID_RE = re.compile(r"^[A-Za-z0-9_.-]{2,100}$")
    _RUN_RE = re.compile(r"^[A-Za-z0-9_.-]{8,128}$")
    _SHA_RE = re.compile(r"^[0-9a-f]{64}$")

    @classmethod
    def from_environment(
        cls,
        expected_engine: EngineType,
        *,
        repo_root: str | Path = ".",
    ) -> "PipelineAdapterRuntime":
        root = Path(repo_root).resolve()
        mode = os.environ.get("EXECUTION_MODE", "").strip().upper()
        if mode not in {"RESEARCH", "PAPER"}:
            raise AdapterRuntimeError(f"unsafe_execution_mode:{mode or 'missing'}")

        engine_name = os.environ.get("TRADEBOT_PIPELINE_ENGINE", "").strip().upper()
        if engine_name != expected_engine.value:
            raise AdapterRuntimeError("pipeline_engine_identity_mismatch")
        strategy_id = os.environ.get("TRADEBOT_PIPELINE_STRATEGY_ID", "").strip()
        run_id = os.environ.get("TRADEBOT_PIPELINE_RUN_ID", "").strip()
        if not cls._ID_RE.fullmatch(strategy_id):
            raise AdapterRuntimeError("invalid_pipeline_strategy_id")
        if not cls._RUN_RE.fullmatch(run_id):
            raise AdapterRuntimeError("invalid_pipeline_run_id")

        raw_result = os.environ.get("TRADEBOT_PIPELINE_RESULT_MANIFEST", "").strip()
        if not raw_result:
            raise AdapterRuntimeError("pipeline_result_manifest_required")
        result_manifest = Path(raw_result).expanduser().resolve()
        expected_parent = root / "runtime" / "strategy_pipeline" / strategy_id / run_id
        expected_name = f"{expected_engine.value.lower()}.result.json"
        if result_manifest.parent != expected_parent or result_manifest.name != expected_name:
            raise AdapterRuntimeError("pipeline_result_manifest_path_invalid")

        raw_hashes = os.environ.get("TRADEBOT_PIPELINE_INPUT_HASHES_JSON", "").strip()
        try:
            parsed = json.loads(raw_hashes)
        except json.JSONDecodeError as exc:
            raise AdapterRuntimeError("pipeline_input_hashes_invalid_json") from exc
        if not isinstance(parsed, Mapping):
            raise AdapterRuntimeError("pipeline_input_hashes_must_be_object")

        input_hashes: dict[str, str] = {}
        for raw_path, raw_digest in parsed.items():
            path = Path(str(raw_path)).expanduser().resolve()
            digest = str(raw_digest or "").strip()
            if not path.is_file():
                raise AdapterRuntimeError(f"pipeline_input_missing:{path}")
            if not cls._SHA_RE.fullmatch(digest):
                raise AdapterRuntimeError(f"pipeline_input_hash_invalid:{path}")
            if sha256_file(path) != digest:
                raise AdapterRuntimeError(f"pipeline_input_hash_mismatch:{path}")
            input_hashes[str(path)] = digest

        return cls(
            repo_root=root,
            engine=expected_engine,
            run_id=run_id,
            strategy_id=strategy_id,
            result_manifest=result_manifest,
            input_hashes=input_hashes,
        )

    @property
    def run_root(self) -> Path:
        return self.result_manifest.parent

    def write_json_artifact(self, filename: str, payload: Mapping[str, Any]) -> Path:
        if Path(filename).name != filename or not filename.endswith(".json"):
            raise AdapterRuntimeError("adapter_artifact_filename_invalid")
        target = self.run_root / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(
            json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp.replace(target)
        return target

    def write_success(
        self,
        *,
        artifact: str | Path,
        verdict: str,
        metrics: EngineMetrics | None = None,
        limitations: list[str] | None = None,
    ) -> EngineResult:
        path = Path(artifact).resolve()
        if not path.is_file() or path.parent != self.run_root:
            raise AdapterRuntimeError("adapter_success_artifact_invalid")
        result = EngineResult(
            engine=self.engine,
            state=PipelineState.SUCCESS,
            run_id=self.run_id,
            strategy_id=self.strategy_id,
            artifacts_generated=[str(path)],
            input_hashes=dict(self.input_hashes),
            output_hashes={str(path): sha256_file(path)},
            limitations=list(limitations or []),
            verdict=str(verdict or "").strip(),
            exit_code=0,
            verified=True,
            created_timestamp=_utc_now(),
            metrics=metrics or EngineMetrics(),
        )
        if not result.verdict:
            raise AdapterRuntimeError("adapter_success_verdict_required")
        write_engine_result_manifest(self.result_manifest, result)
        result.manifest_path = str(self.result_manifest)
        return result

    def write_blocked(
        self,
        *,
        verdict: str,
        blockers: list[str],
        artifact: str | Path | None = None,
    ) -> EngineResult:
        artifacts: list[str] = []
        output_hashes: dict[str, str] = {}
        if artifact is not None:
            path = Path(artifact).resolve()
            if not path.is_file() or path.parent != self.run_root:
                raise AdapterRuntimeError("adapter_blocked_artifact_invalid")
            artifacts = [str(path)]
            output_hashes = {str(path): sha256_file(path)}
        result = EngineResult(
            engine=self.engine,
            state=PipelineState.BLOCKED,
            run_id=self.run_id,
            strategy_id=self.strategy_id,
            artifacts_generated=artifacts,
            input_hashes=dict(self.input_hashes),
            output_hashes=output_hashes,
            blockers=list(blockers),
            verdict=str(verdict or "").strip(),
            exit_code=0,
            verified=True,
            created_timestamp=_utc_now(),
        )
        if not result.verdict or not result.blockers:
            raise AdapterRuntimeError("adapter_blocked_reason_required")
        write_engine_result_manifest(self.result_manifest, result)
        result.manifest_path = str(self.result_manifest)
        return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "AdapterRuntimeError",
    "PipelineAdapterRuntime",
]

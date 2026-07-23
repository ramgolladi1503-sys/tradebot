from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
from typing import Iterable

from core.strategy_pipeline.pipeline_context import PipelineContext
from core.strategy_pipeline.pipeline_models import EngineResult, EngineType, PipelineState
from core.strategy_pipeline.pipeline_state import PipelineStateTracker
from core.strategy_pipeline.result_manifest import sha256_file


class PipelineValidationError(ValueError):
    """Raised when pipeline execution or evidence violates a fail-closed contract."""


class PipelineValidator:
    """Validates research-only execution and machine-verifiable engine evidence."""

    _SAFE_MODES = {"RESEARCH", "PAPER"}
    _ID_RE = re.compile(r"^[A-Za-z0-9_.-]{2,100}$")
    _RUN_RE = re.compile(r"^[A-Za-z0-9_.-]{8,128}$")
    _SHA_RE = re.compile(r"^[0-9a-f]{64}$")

    @staticmethod
    def _safe_relative_path(value: str) -> str:
        text = str(value or "").strip().replace("\\", "/")
        path = PurePosixPath(text)
        if not text or path.is_absolute() or ".." in path.parts:
            raise PipelineValidationError(f"unsafe_relative_path:{text or 'missing'}")
        return path.as_posix()

    def validate_pre_run(self, strategy_id: str, context: PipelineContext) -> None:
        if not self._ID_RE.fullmatch(str(strategy_id or "")):
            raise PipelineValidationError("invalid_strategy_id")
        if not self._RUN_RE.fullmatch(str(context.run_id or "")):
            raise PipelineValidationError("invalid_run_id")

        mode = str(context.execution_mode or "").upper()
        if mode not in self._SAFE_MODES:
            raise PipelineValidationError(f"unsafe_execution_mode:{mode or 'missing'}")
        for variable in ("EXECUTION_MODE", "TRADING_MODE"):
            if os.environ.get(variable, "").strip().upper() == "LIVE":
                raise PipelineValidationError(f"live_environment_forbidden:{variable}")

        self._safe_relative_path(context.reports_dir)
        if not context.allowed_output_roots:
            raise PipelineValidationError("allowed_output_roots_required")
        for root in context.allowed_output_roots:
            self._safe_relative_path(root)

        normalized_inputs: dict[str, dict[str, str]] = {}
        for engine_name, raw_paths in context.engine_inputs.items():
            try:
                engine = EngineType(str(engine_name).upper())
            except ValueError as exc:
                raise PipelineValidationError(f"unknown_engine_input:{engine_name}") from exc
            hashes: dict[str, str] = {}
            for raw_path in raw_paths:
                path = Path(raw_path).expanduser().resolve()
                if not path.is_file():
                    raise PipelineValidationError(
                        f"engine_input_missing:{engine.value}:{raw_path}"
                    )
                hashes[str(path)] = sha256_file(path)
            normalized_inputs[engine.value] = hashes
        context.engine_input_hashes = normalized_inputs
        context.strategy_id = strategy_id

    def validate_engine_result(
        self,
        result: EngineResult,
        engine: EngineType,
        strategy_id: str,
        context: PipelineContext,
        *,
        base_dir: str | Path,
    ) -> None:
        if result.engine != engine:
            raise PipelineValidationError("engine_result_engine_mismatch")
        if result.strategy_id != strategy_id:
            raise PipelineValidationError("engine_result_strategy_mismatch")
        if result.run_id != context.run_id:
            raise PipelineValidationError("engine_result_run_mismatch")

        expected_inputs = context.engine_input_hashes.get(engine.value, {})
        if result.input_hashes != expected_inputs:
            raise PipelineValidationError("engine_result_input_hash_mismatch")

        if result.state == PipelineState.SUCCESS:
            if context.require_verified_results and not result.verified:
                raise PipelineValidationError("success_result_not_verified")
            if not str(result.verdict or "").strip():
                raise PipelineValidationError("success_result_verdict_required")
            if result.exit_code not in (0, None if result.cached else 0):
                raise PipelineValidationError("success_result_exit_code_invalid")
            if not result.artifacts_generated:
                raise PipelineValidationError("success_result_artifacts_required")
            self._verify_output_artifacts(result, context, base_dir=base_dir)
        elif result.state in (PipelineState.BLOCKED, PipelineState.FAILED, PipelineState.DEGRADED):
            if not (result.errors or result.blockers or str(result.verdict or "").strip()):
                raise PipelineValidationError("non_success_result_reason_required")
            if result.artifacts_generated or result.output_hashes:
                if not result.artifacts_generated:
                    raise PipelineValidationError("non_success_artifact_paths_required")
                self._verify_output_artifacts(result, context, base_dir=base_dir)

    def _verify_output_artifacts(
        self,
        result: EngineResult,
        context: PipelineContext,
        *,
        base_dir: str | Path,
    ) -> None:
        root = Path(base_dir).resolve()
        allowed = [(root / self._safe_relative_path(item)).resolve() for item in context.allowed_output_roots]
        artifact_paths: list[Path] = []
        for raw in result.artifacts_generated:
            candidate = Path(raw)
            path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
            if not path.is_file():
                raise PipelineValidationError(f"result_artifact_missing:{raw}")
            if not any(path == allowed_root or allowed_root in path.parents for allowed_root in allowed):
                raise PipelineValidationError(f"result_artifact_outside_allowed_roots:{raw}")
            artifact_paths.append(path)

        normalized_hashes = {str(path): sha256_file(path) for path in artifact_paths}
        supplied_hashes: dict[str, str] = {}
        for raw, digest in result.output_hashes.items():
            candidate = Path(raw)
            path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
            if not self._SHA_RE.fullmatch(str(digest or "")):
                raise PipelineValidationError(f"result_artifact_hash_invalid:{raw}")
            supplied_hashes[str(path)] = digest
        if normalized_hashes != supplied_hashes:
            raise PipelineValidationError("result_artifact_hash_mismatch")

    def validate_post_run(
        self,
        tracker: PipelineStateTracker,
        context: PipelineContext,
        required_engines: Iterable[EngineType],
        *,
        base_dir: str | Path,
    ) -> None:
        if tracker.strategy_id != context.strategy_id:
            raise PipelineValidationError("tracker_strategy_mismatch")
        for engine, result in tracker.engine_results.items():
            self.validate_engine_result(
                result,
                engine,
                tracker.strategy_id,
                context,
                base_dir=base_dir,
            )

        required = tuple(required_engines)
        if tracker.global_state == PipelineState.SUCCESS:
            if not required or any(
                tracker.get_engine_state(engine) != PipelineState.SUCCESS for engine in required
            ):
                raise PipelineValidationError("pipeline_success_without_all_required_engines")

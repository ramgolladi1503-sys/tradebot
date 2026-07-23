from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Optional

from core.strategy_pipeline.pipeline_context import PipelineContext
from core.strategy_pipeline.pipeline_models import EngineResult, PipelineState


class PipelineValidationError(RuntimeError):
    """Raised when a strategy-pipeline safety or integrity rule fails."""


class PipelineValidator:
    """Fail-closed safety and artifact-integrity validation."""

    FORBIDDEN_PATH_TOKENS = (
        "broker",
        "orders",
        "execution",
        "credentials",
        "access_token",
        "live_config",
    )

    @staticmethod
    def sha256(path: str | Path) -> str:
        candidate = Path(path)
        if not candidate.is_file():
            raise PipelineValidationError(f"Artifact missing: {candidate}")
        digest = hashlib.sha256()
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def validate_pre_run(
        cls,
        context: Optional[PipelineContext] = None,
        changed_paths: Optional[Iterable[str]] = None,
    ) -> None:
        # Backward-compatible no-argument call remains valid for legacy tests.
        if context is None:
            return
        if not context.paper_only:
            raise PipelineValidationError("Strategy research pipeline is paper-only")
        if not context.strategy_id or not context.strategy_id.strip():
            raise PipelineValidationError("strategy_id is required")
        if not context.run_id or not context.run_id.strip():
            raise PipelineValidationError("run_id is required")
        for path in changed_paths or ():
            lowered = str(path).lower()
            if any(token in lowered for token in cls.FORBIDDEN_PATH_TOKENS):
                raise PipelineValidationError(f"Forbidden runtime path in research scope: {path}")

    @classmethod
    def validate_input_file(cls, path: str | Path, expected_sha256: Optional[str] = None) -> str:
        actual = cls.sha256(path)
        if expected_sha256 and actual != expected_sha256:
            raise PipelineValidationError(
                f"Artifact hash mismatch for {path}: expected {expected_sha256}, found {actual}"
            )
        return actual

    @classmethod
    def validate_engine_result(cls, result: EngineResult) -> None:
        if result.state == PipelineState.SUCCESS:
            if not result.run_id or not result.strategy_id:
                raise PipelineValidationError(f"{result.engine.value} success lacks run provenance")
            if result.exit_code not in (None, 0):
                raise PipelineValidationError(f"{result.engine.value} success has non-zero exit code")
            if not result.verdict:
                raise PipelineValidationError(f"{result.engine.value} success lacks a verdict")
            if result.engine.value != "REGISTRY" and not result.output_hashes:
                raise PipelineValidationError(f"{result.engine.value} success lacks verified outputs")
        if result.state in (PipelineState.BLOCKED, PipelineState.FAILED) and not (
            result.errors or result.blockers
        ):
            raise PipelineValidationError(f"{result.engine.value} failure lacks reason")

    @classmethod
    def validate_post_run(cls, results: Optional[Iterable[EngineResult]] = None) -> None:
        if results is None:
            return
        for result in results:
            cls.validate_engine_result(result)

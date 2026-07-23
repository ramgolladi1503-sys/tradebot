from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Optional

from core.strategy_pipeline.artifact_locator import ArtifactLocator
from core.strategy_pipeline.dependency_resolver import DependencyResolver
from core.strategy_pipeline.pipeline_context import PipelineContext
from core.strategy_pipeline.pipeline_models import (
    EngineResult,
    EngineType,
    FinalDecision,
    PipelineState,
)
from core.strategy_pipeline.pipeline_state import PipelineStateTracker
from core.strategy_pipeline.pipeline_validator import PipelineValidationError, PipelineValidator
from core.strategy_pipeline.result_manifest import (
    ResultManifestError,
    load_engine_result_manifest,
    sha256_file,
)

logger = logging.getLogger(__name__)


class StrategyPipelineEngine:
    """Fail-closed orchestrator for the strategy research engines.

    An exit code or a file path is never treated as success by itself. Every
    successful stage must return a run-scoped, hash-verified result manifest.
    """

    _SCRIPT_MAP = {
        EngineType.RESEARCH: "scripts/run_research_registry.py",
        EngineType.REGISTRY: None,
        EngineType.TRUTH: "scripts/run_strategy_truth_audit.py",
        EngineType.OUTCOMES: "scripts/run_outcome_evidence_replay.py",
        EngineType.STATISTICS: "scripts/run_statistical_validation.py",
        EngineType.CERTIFICATION: "scripts/run_strategy_certification.py",
        EngineType.DRIFT: "scripts/run_live_drift.py",
    }

    def __init__(
        self,
        locator: Optional[ArtifactLocator] = None,
        resolver: Optional[DependencyResolver] = None,
        validator: Optional[PipelineValidator] = None,
    ):
        self.locator = locator or ArtifactLocator()
        self.resolver = resolver or DependencyResolver()
        self.validator = validator or PipelineValidator()

    def run(self, strategy_id: str, context: PipelineContext) -> PipelineStateTracker:
        self.validator.validate_pre_run(strategy_id, context)
        engines = self._engine_sequence(context)
        tracker = PipelineStateTracker(
            strategy_id=strategy_id,
            global_state=PipelineState.RUNNING,
        )

        for engine in engines:
            if not self.resolver.can_run(engine, tracker):
                result = self._blocked_result(
                    engine,
                    strategy_id,
                    context,
                    verdict="DEPENDENCY_NOT_VERIFIED",
                    blockers=["Required upstream engine did not produce verified SUCCESS"],
                )
                tracker.update_engine_result(engine, result)
                break

            lineage_block = self._bind_upstream_inputs(
                engine,
                strategy_id,
                context,
                tracker,
            )
            if lineage_block is not None:
                tracker.update_engine_result(engine, lineage_block)
                break

            result = self._run_engine(engine, strategy_id, context)
            try:
                self.validator.validate_engine_result(
                    result,
                    engine,
                    strategy_id,
                    context,
                    base_dir=self.locator.base_dir,
                )
            except PipelineValidationError as exc:
                result = EngineResult(
                    engine=engine,
                    state=PipelineState.FAILED,
                    run_id=context.run_id,
                    strategy_id=strategy_id,
                    input_hashes=context.engine_input_hashes.get(engine.value, {}),
                    errors=[f"RESULT_VALIDATION_FAILED:{exc}"],
                    verdict="INVALID_ENGINE_RESULT",
                    command=list(result.command),
                    exit_code=result.exit_code,
                    manifest_path=result.manifest_path,
                    created_timestamp=self._now(),
                )
            tracker.update_engine_result(engine, result)
            if result.state in (PipelineState.FAILED, PipelineState.BLOCKED):
                break

        tracker.finalize(engines)
        tracker.final_decision = self._final_decision(tracker)
        self.validator.validate_post_run(
            tracker,
            context,
            engines,
            base_dir=self.locator.base_dir,
        )
        return tracker

    def _engine_sequence(self, context: PipelineContext) -> tuple[EngineType, ...]:
        engines = (
            EngineType.RESEARCH,
            EngineType.REGISTRY,
            EngineType.TRUTH,
            EngineType.OUTCOMES,
            EngineType.STATISTICS,
            EngineType.CERTIFICATION,
        )
        return engines + ((EngineType.DRIFT,) if context.include_drift else ())

    def _bind_upstream_inputs(
        self,
        engine: EngineType,
        strategy_id: str,
        context: PipelineContext,
        tracker: PipelineStateTracker,
    ) -> EngineResult | None:
        expected = dict(context.engine_input_hashes.get(engine.value, {}))
        for dependency in self.resolver.dependencies.get(engine, []):
            upstream = tracker.engine_results.get(dependency)
            if upstream is None or upstream.state != PipelineState.SUCCESS:
                return self._blocked_result(
                    engine,
                    strategy_id,
                    context,
                    verdict="UPSTREAM_RESULT_NOT_SUCCESSFUL",
                    blockers=[dependency.value],
                )
            raw_manifest = str(upstream.manifest_path or "").strip()
            if not raw_manifest:
                return self._blocked_result(
                    engine,
                    strategy_id,
                    context,
                    verdict="UPSTREAM_MANIFEST_MISSING",
                    blockers=[dependency.value],
                )
            candidate = Path(raw_manifest)
            manifest = (
                candidate.resolve()
                if candidate.is_absolute()
                else (self.locator.base_dir / candidate).resolve()
            )
            if not manifest.is_file():
                return self._blocked_result(
                    engine,
                    strategy_id,
                    context,
                    verdict="UPSTREAM_MANIFEST_NOT_FOUND",
                    blockers=[str(manifest)],
                )
            expected[str(manifest)] = sha256_file(manifest)
        context.engine_input_hashes[engine.value] = expected
        return None

    def _run_engine(
        self,
        engine: EngineType,
        strategy_id: str,
        context: PipelineContext,
    ) -> EngineResult:
        logger.info("Running Engine: %s", engine.value)
        expected_inputs = context.engine_input_hashes.get(engine.value, {})

        if not context.force_refresh and engine.value in context.cache_manifests:
            cache_path = Path(context.cache_manifests[engine.value])
            try:
                cached = load_engine_result_manifest(cache_path)
            except ResultManifestError as exc:
                return self._blocked_result(
                    engine,
                    strategy_id,
                    context,
                    verdict="CACHE_MANIFEST_INVALID",
                    blockers=[str(exc)],
                )
            cached.cached = True
            cached.manifest_path = str(cache_path)
            return cached

        if context.dry_run:
            return self._blocked_result(
                engine,
                strategy_id,
                context,
                verdict="REPORTS_ONLY_ARTIFACT_MISSING",
                blockers=["Artifact missing in reports-only mode"],
            )

        script_path = self._SCRIPT_MAP.get(engine)
        if not script_path:
            return self._blocked_result(
                engine,
                strategy_id,
                context,
                verdict="ENGINE_ADAPTER_MISSING",
                blockers=[f"No truthful adapter is implemented for {engine.value}"],
            )
        absolute_script = (self.locator.base_dir / script_path).resolve()
        if not absolute_script.is_file():
            return self._blocked_result(
                engine,
                strategy_id,
                context,
                verdict="ENGINE_SCRIPT_MISSING",
                blockers=[script_path],
            )

        command_or_blocker = self._build_command(engine, strategy_id, context, script_path)
        if isinstance(command_or_blocker, EngineResult):
            return command_or_blocker
        command = command_or_blocker

        result_manifest = self.locator.result_manifest_path(
            engine,
            strategy_id,
            context.run_id,
        )
        env = os.environ.copy()
        env.update(
            {
                "EXECUTION_MODE": context.execution_mode.upper(),
                "TRADEBOT_PIPELINE_RUN_ID": context.run_id,
                "TRADEBOT_PIPELINE_STRATEGY_ID": strategy_id,
                "TRADEBOT_PIPELINE_ENGINE": engine.value,
                "TRADEBOT_PIPELINE_RESULT_MANIFEST": str(result_manifest),
                "TRADEBOT_PIPELINE_INPUT_HASHES_JSON": json.dumps(
                    expected_inputs,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
        proc = subprocess.run(
            command,
            cwd=self.locator.base_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            error = (proc.stderr or proc.stdout or "engine process failed").strip()
            return EngineResult(
                engine=engine,
                state=PipelineState.FAILED,
                run_id=context.run_id,
                strategy_id=strategy_id,
                input_hashes=expected_inputs,
                errors=[error],
                verdict="ENGINE_PROCESS_FAILED",
                command=command,
                exit_code=proc.returncode,
                created_timestamp=self._now(),
            )

        if not result_manifest.is_file():
            return self._blocked_result(
                engine,
                strategy_id,
                context,
                verdict="RESULT_MANIFEST_MISSING",
                blockers=[str(result_manifest)],
                command=command,
                exit_code=proc.returncode,
            )
        try:
            loaded = load_engine_result_manifest(result_manifest)
        except ResultManifestError as exc:
            return self._blocked_result(
                engine,
                strategy_id,
                context,
                verdict="RESULT_MANIFEST_INVALID",
                blockers=[str(exc)],
                command=command,
                exit_code=proc.returncode,
            )
        loaded.command = command
        loaded.exit_code = proc.returncode
        loaded.manifest_path = str(result_manifest)
        return loaded

    def _build_command(
        self,
        engine: EngineType,
        strategy_id: str,
        context: PipelineContext,
        script_path: str,
    ) -> list[str] | EngineResult:
        command = [sys.executable, script_path]
        explicit_args = context.engine_args.get(engine.value)
        if engine in (EngineType.OUTCOMES, EngineType.STATISTICS):
            if not explicit_args:
                return self._blocked_result(
                    engine,
                    strategy_id,
                    context,
                    verdict="ENGINE_ARGUMENTS_MISSING",
                    blockers=[
                        f"Exact {engine.value} input arguments are required; latest-file discovery is forbidden"
                    ],
                )
            command.extend(explicit_args)
        elif engine == EngineType.RESEARCH:
            if explicit_args:
                command.extend(explicit_args)
        else:
            command.extend(["--strategy", strategy_id])
            if explicit_args:
                command.extend(explicit_args)
        return command

    def _blocked_result(
        self,
        engine: EngineType,
        strategy_id: str,
        context: PipelineContext,
        *,
        verdict: str,
        blockers: list[str],
        command: Optional[list[str]] = None,
        exit_code: Optional[int] = None,
    ) -> EngineResult:
        return EngineResult(
            engine=engine,
            state=PipelineState.BLOCKED,
            run_id=context.run_id,
            strategy_id=strategy_id,
            input_hashes=context.engine_input_hashes.get(engine.value, {}),
            blockers=blockers,
            verdict=verdict,
            command=list(command or []),
            exit_code=exit_code,
            created_timestamp=self._now(),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    @staticmethod
    def _final_decision(tracker: PipelineStateTracker) -> FinalDecision:
        if tracker.global_state in (PipelineState.BLOCKED, PipelineState.FAILED):
            failing_engine = tracker.blocked_at
            if failing_engine is None:
                for engine, result in tracker.engine_results.items():
                    if result.state == PipelineState.FAILED:
                        failing_engine = engine
                        break
            result = tracker.engine_results.get(failing_engine) if failing_engine else None
            reason = (
                (result.verdict if result else None)
                or (result.errors[0] if result and result.errors else None)
                or "PIPELINE_EXECUTION_INCOMPLETE"
            )
            blockers = list(result.blockers if result else [])
            if result and result.errors:
                blockers.extend(result.errors)
            return FinalDecision(
                strategy_id=tracker.strategy_id,
                certification_status=(
                    "Blocked" if tracker.global_state == PipelineState.BLOCKED else "Failed"
                ),
                reason=reason,
                blockers=blockers,
                limitations=list(result.limitations if result else []),
            )
        if tracker.global_state == PipelineState.DEGRADED:
            return FinalDecision(
                strategy_id=tracker.strategy_id,
                certification_status="Research Only",
                reason="PIPELINE_DEGRADED",
                blockers=[],
                limitations=["One or more engines reported degraded evidence"],
            )
        return FinalDecision(
            strategy_id=tracker.strategy_id,
            certification_status="Research Only",
            reason="VERIFIED_RESEARCH_PIPELINE_COMPLETE",
            blockers=[],
            limitations=["No live execution authority is granted"],
        )

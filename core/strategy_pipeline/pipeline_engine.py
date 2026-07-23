from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path
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

logger = logging.getLogger(__name__)


class StrategyPipelineEngine:
    """Fail-closed orchestrator for the research and paper-certification engines."""

    def __init__(
        self,
        locator: Optional[ArtifactLocator] = None,
        resolver: Optional[DependencyResolver] = None,
    ):
        self.locator = locator or ArtifactLocator()
        self.resolver = resolver or DependencyResolver()
        self.validator = PipelineValidator()

    def run(self, strategy_id: str, context: PipelineContext) -> PipelineStateTracker:
        context.strategy_id = strategy_id
        context.run_id = context.run_id or str(uuid.uuid4())
        self.validator.validate_pre_run(context)

        tracker = PipelineStateTracker(strategy_id=strategy_id, global_state=PipelineState.RUNNING)
        engines = [
            EngineType.RESEARCH,
            EngineType.REGISTRY,
            EngineType.TRUTH,
            EngineType.OUTCOMES,
            EngineType.STATISTICS,
            EngineType.CERTIFICATION,
        ]
        if bool(context.get_artifact("include_drift")):
            engines.append(EngineType.DRIFT)

        for engine in engines:
            if not self.resolver.can_run(engine, tracker):
                result = EngineResult(
                    engine=engine,
                    state=PipelineState.BLOCKED,
                    run_id=context.run_id,
                    strategy_id=strategy_id,
                    verdict="DEPENDENCY_BLOCKED",
                    blockers=["One or more prerequisite engines did not succeed"],
                )
                tracker.update_engine_result(engine, result)
                break

            result = self._run_engine(engine, strategy_id, context)
            try:
                self.validator.validate_engine_result(result)
            except PipelineValidationError as exc:
                result = EngineResult(
                    engine=engine,
                    state=PipelineState.FAILED,
                    run_id=context.run_id,
                    strategy_id=strategy_id,
                    verdict="INVALID_ENGINE_RESULT",
                    errors=[str(exc)],
                )
            tracker.update_engine_result(engine, result)
            if result.state in (PipelineState.FAILED, PipelineState.BLOCKED):
                break

        if tracker.global_state == PipelineState.RUNNING:
            tracker.global_state = PipelineState.SUCCESS
        self._set_final_decision(tracker)
        self.validator.validate_post_run(tracker.engine_results.values())
        return tracker

    def _set_final_decision(self, tracker: PipelineStateTracker) -> None:
        if tracker.global_state == PipelineState.BLOCKED:
            tracker.final_decision = FinalDecision(
                strategy_id=tracker.strategy_id,
                certification_status="Blocked",
                reason=f"Blocked at {tracker.blocked_at.value if tracker.blocked_at else 'Unknown'}",
                blockers=[
                    blocker
                    for result in tracker.engine_results.values()
                    for blocker in (result.blockers or result.errors)
                ],
            )
        elif tracker.global_state == PipelineState.FAILED:
            tracker.final_decision = FinalDecision(
                strategy_id=tracker.strategy_id,
                certification_status="Failed",
                reason="Pipeline execution or integrity validation failed",
                blockers=[
                    error
                    for result in tracker.engine_results.values()
                    for error in (result.errors or result.blockers)
                ],
            )
        else:
            tracker.final_decision = FinalDecision(
                strategy_id=tracker.strategy_id,
                certification_status="Paper Eligible Review",
                reason="All configured research stages produced verified artifacts.",
                limitations=["Not approved for live execution"],
            )

    def _run_engine(self, engine: EngineType, strategy_id: str, context: PipelineContext) -> EngineResult:
        logger.info("Running engine: %s", engine.value)
        cached = None if context.force_refresh else self._load_verified_cache(engine, strategy_id, context)
        if cached is not None:
            return cached
        if context.dry_run:
            return self._blocked(engine, strategy_id, context, "DRY_RUN_HAS_NO_VERIFIED_ARTIFACT")

        if engine == EngineType.REGISTRY:
            contract = self.locator.locate_strategy_contract(strategy_id)
            if not contract:
                return self._blocked(engine, strategy_id, context, "STRATEGY_CONTRACT_MISSING")
            digest = self.validator.validate_input_file(contract)
            return EngineResult(
                engine=engine,
                state=PipelineState.SUCCESS,
                run_id=context.run_id,
                strategy_id=strategy_id,
                verdict="REGISTRY_CONTRACT_FOUND",
                exit_code=0,
                artifacts_generated=[str(contract)],
                output_hashes={str(contract): digest},
                created_timestamp=str(time.time()),
            )

        command = self._build_command(engine, strategy_id, context)
        if command is None:
            return self._blocked(engine, strategy_id, context, "ENGINE_INPUT_CONTRACT_INCOMPLETE")
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            return EngineResult(
                engine=engine,
                state=PipelineState.FAILED,
                run_id=context.run_id,
                strategy_id=strategy_id,
                verdict="PROCESS_FAILED",
                command=command,
                exit_code=completed.returncode,
                errors=[completed.stderr.strip() or completed.stdout.strip() or "Engine process failed"],
            )

        output_key = f"{engine.value.lower()}_output"
        output_path = context.get_artifact(output_key)
        if not output_path:
            return self._blocked(
                engine,
                strategy_id,
                context,
                f"VERIFIED_OUTPUT_PATH_REQUIRED:{output_key}",
                command=command,
            )
        try:
            digest = self.validator.validate_input_file(output_path)
        except PipelineValidationError as exc:
            return self._blocked(engine, strategy_id, context, str(exc), command=command)

        return EngineResult(
            engine=engine,
            state=PipelineState.SUCCESS,
            run_id=context.run_id,
            strategy_id=strategy_id,
            verdict="VERIFIED_OUTPUT",
            command=command,
            exit_code=0,
            artifacts_generated=[str(output_path)],
            output_hashes={str(output_path): digest},
            created_timestamp=str(time.time()),
        )

    def _build_command(self, engine: EngineType, strategy_id: str, context: PipelineContext) -> Optional[list[str]]:
        if engine == EngineType.RESEARCH:
            return ["python", "scripts/run_research_registry.py"]
        if engine == EngineType.TRUTH:
            return ["python", "scripts/run_strategy_truth_audit.py", "--strategy", strategy_id, "--json"]
        if engine == EngineType.OUTCOMES:
            candidate = context.get_artifact("candidate_file")
            trace = context.get_artifact("option_trace")
            if not candidate or not trace:
                return None
            return [
                "python",
                "scripts/run_outcome_evidence_replay.py",
                "--candidate-file",
                str(candidate),
                "--option-trace",
                str(trace),
                "--json",
            ]
        if engine == EngineType.STATISTICS:
            evidence = context.get_artifact("outcome_evidence_file")
            if not evidence:
                return None
            return ["python", "scripts/run_statistical_validation.py", "--evidence-file", str(evidence)]
        if engine == EngineType.CERTIFICATION:
            return ["python", "scripts/run_strategy_certification.py", "--strategy", strategy_id]
        if engine == EngineType.DRIFT:
            if not context.get_artifact("certified_baseline") or not context.get_artifact("paper_snapshot"):
                return None
            return ["python", "scripts/run_live_drift.py", "--strategy", strategy_id]
        return None

    def _load_verified_cache(
        self,
        engine: EngineType,
        strategy_id: str,
        context: PipelineContext,
    ) -> Optional[EngineResult]:
        artifact = self._get_cached_path(engine, strategy_id)
        if not artifact:
            return None
        manifest_path = Path(f"{artifact}.manifest.json")
        if not manifest_path.is_file():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("strategy_id") != strategy_id or manifest.get("engine") != engine.value:
                return None
            expected = manifest.get("artifact_sha256")
            actual = self.validator.validate_input_file(artifact, expected)
        except (OSError, ValueError, PipelineValidationError):
            return None
        return EngineResult(
            engine=engine,
            state=PipelineState.SUCCESS,
            run_id=context.run_id,
            strategy_id=strategy_id,
            verdict="VERIFIED_CACHE",
            cached=True,
            exit_code=0,
            artifacts_generated=[str(artifact)],
            output_hashes={str(artifact): actual},
            created_timestamp=str(time.time()),
        )

    def _blocked(
        self,
        engine: EngineType,
        strategy_id: str,
        context: PipelineContext,
        reason: str,
        command: Optional[list[str]] = None,
    ) -> EngineResult:
        return EngineResult(
            engine=engine,
            state=PipelineState.BLOCKED,
            run_id=context.run_id,
            strategy_id=strategy_id,
            verdict="BLOCKED",
            command=command or [],
            blockers=[reason],
        )

    def _get_cached_path(self, engine: EngineType, strategy_id: str) -> Optional[str]:
        methods = {
            EngineType.RESEARCH: self.locator.locate_research_hypothesis,
            EngineType.REGISTRY: self.locator.locate_strategy_contract,
            EngineType.TRUTH: self.locator.locate_truth_report,
            EngineType.OUTCOMES: self.locator.locate_evidence_file,
            EngineType.STATISTICS: self.locator.locate_statistics_report,
            EngineType.CERTIFICATION: self.locator.locate_certification_report,
            EngineType.DRIFT: self.locator.locate_live_drift_report,
        }
        path = methods[engine](strategy_id)
        return str(path) if path else None

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.governed_strategy_research import (
    GovernedResearchStore,
    ResearchError,
    ResearchState,
    SAFETY_ASSERTIONS,
)
from core.strategy_pipeline.adapter_runtime import PipelineAdapterRuntime
from core.strategy_pipeline.pipeline_models import EngineMetrics, EngineResult
from core.strategy_pipeline.result_manifest import sha256_file


class ResearchStageError(ValueError):
    """Raised when governed research cannot satisfy the pipeline Research stage."""


_ALLOWED_RESEARCH_STATES = {
    ResearchState.HYPOTHESIS_FROZEN.value,
    ResearchState.IMPLEMENTED.value,
    ResearchState.AUDITED.value,
    ResearchState.VALIDATED.value,
    ResearchState.PAPER_ELIGIBLE.value,
}


def run_research_stage(
    runtime: PipelineAdapterRuntime,
    *,
    governed_run_dir: str | Path,
) -> EngineResult:
    run_root = Path(governed_run_dir).expanduser().resolve()
    manifest_path = run_root / "manifest.json"
    hypothesis_path = run_root / "hypothesis_frozen.json"
    expected_inputs = {str(manifest_path), str(hypothesis_path)}
    supplied_inputs = set(runtime.input_hashes)
    if supplied_inputs != expected_inputs:
        raise ResearchStageError(
            "research_inputs_must_be_exact_governed_manifest_and_frozen_hypothesis"
        )

    store = GovernedResearchStore(run_root)
    try:
        status = store.verify_integrity()
    except ResearchError as exc:
        raise ResearchStageError(f"governed_research_unreadable:{exc}") from exc
    if not status.integrity_ok:
        raise ResearchStageError(
            "governed_research_integrity_invalid:" + ",".join(status.blockers)
        )
    if status.strategy_id != runtime.strategy_id:
        raise ResearchStageError("governed_research_strategy_mismatch")
    if status.state not in _ALLOWED_RESEARCH_STATES:
        raise ResearchStageError(f"governed_research_state_not_eligible:{status.state}")
    if status.allowed_for_live_execution:
        raise ResearchStageError("governed_research_live_authority_forbidden")

    hypothesis = _load_json(hypothesis_path)
    if hypothesis.get("strategy_id") != runtime.strategy_id:
        raise ResearchStageError("frozen_hypothesis_strategy_mismatch")
    if hypothesis.get("run_id") != status.run_id:
        raise ResearchStageError("frozen_hypothesis_run_mismatch")
    if hypothesis.get("contract_sha256") != status.hypothesis_sha256:
        raise ResearchStageError("frozen_hypothesis_contract_hash_mismatch")
    if hypothesis.get("outcomes_observed") is not False:
        raise ResearchStageError("frozen_hypothesis_outcomes_boundary_invalid")
    if hypothesis.get("tunable_after_freeze") is not False:
        raise ResearchStageError("frozen_hypothesis_tuning_boundary_invalid")

    artifact_payload: dict[str, Any] = {
        "schema_version": 1,
        "engine": "RESEARCH",
        "pipeline_run_id": runtime.run_id,
        "governed_research_run_id": status.run_id,
        "strategy_id": runtime.strategy_id,
        "decision": "FROZEN_HYPOTHESIS_VERIFIED",
        "governed_state": status.state,
        "hypothesis_sha256": status.hypothesis_sha256,
        "governed_manifest_file_sha256": sha256_file(manifest_path),
        "frozen_hypothesis_file_sha256": sha256_file(hypothesis_path),
        "frozen_at": hypothesis.get("frozen_at"),
        "market": hypothesis.get("market"),
        "timeframe": hypothesis.get("timeframe"),
        "data_universe": hypothesis.get("data_universe"),
        "development_window": hypothesis.get("development_window"),
        "holdout_window": hypothesis.get("holdout_window"),
        "primary_metric": hypothesis.get("primary_metric"),
        "negative_control_count": len(hypothesis.get("negative_controls") or []),
        "outcomes_observed": False,
        "tunable_after_freeze": False,
        "allowed_for_paper": status.allowed_for_paper,
        "allowed_for_live_execution": False,
        "safety": dict(SAFETY_ASSERTIONS),
    }
    artifact = runtime.write_json_artifact("research.stage.json", artifact_payload)
    return runtime.write_success(
        artifact=artifact,
        verdict="FROZEN_HYPOTHESIS_VERIFIED",
        metrics=EngineMetrics(strategies_loaded=1),
        limitations=[
            "Research-stage acceptance proves frozen hypothesis integrity only; it does not prove edge."
        ],
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchStageError(f"research_json_unreadable:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise ResearchStageError(f"research_json_must_be_object:{path}")
    return payload


__all__ = ["ResearchStageError", "run_research_stage"]

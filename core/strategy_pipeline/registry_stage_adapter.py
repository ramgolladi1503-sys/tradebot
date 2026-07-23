from __future__ import annotations

import dataclasses
from datetime import date, datetime
from enum import Enum
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from core.strategy_pipeline.adapter_runtime import PipelineAdapterRuntime
from core.strategy_pipeline.pipeline_models import EngineMetrics, EngineResult, EngineType, PipelineState
from core.strategy_pipeline.result_manifest import load_engine_result_manifest, sha256_file
from core.strategy_registry.strategy_contract import StrategyContract
from core.strategy_registry.strategy_manifest import StrategyManifest


class RegistryStageError(ValueError):
    """Raised when an exact strategy contract cannot be proven."""


def run_registry_stage(
    runtime: PipelineAdapterRuntime,
    *,
    implementation_file: str | Path,
) -> EngineResult:
    implementation = Path(implementation_file).expanduser().resolve()
    strategies_root = (runtime.repo_root / "strategies").resolve()
    if not implementation.is_file() or strategies_root not in implementation.parents:
        raise RegistryStageError("implementation_file_must_exist_under_strategies")
    if implementation.suffix != ".py" or implementation.name.startswith("__"):
        raise RegistryStageError("implementation_file_must_be_strategy_python")

    implementation_key = str(implementation)
    if implementation_key not in runtime.input_hashes:
        raise RegistryStageError("implementation_file_not_declared_as_pipeline_input")
    upstream_paths = [path for path in runtime.input_hashes if path != implementation_key]
    if len(upstream_paths) != 1:
        raise RegistryStageError("registry_requires_exactly_one_research_manifest_input")
    research_manifest_path = Path(upstream_paths[0]).resolve()
    if research_manifest_path.name != "research.result.json":
        raise RegistryStageError("registry_upstream_must_be_research_result_manifest")

    research_result = load_engine_result_manifest(research_manifest_path)
    if (
        research_result.engine != EngineType.RESEARCH
        or research_result.state != PipelineState.SUCCESS
        or research_result.strategy_id != runtime.strategy_id
        or research_result.run_id != runtime.run_id
        or not research_result.verified
    ):
        raise RegistryStageError("research_result_lineage_invalid")
    research_artifact = _verify_single_upstream_artifact(research_result)
    research_payload = _load_json(research_artifact)
    if research_payload.get("strategy_id") != runtime.strategy_id:
        raise RegistryStageError("research_artifact_strategy_mismatch")
    if research_payload.get("decision") != "FROZEN_HYPOTHESIS_VERIFIED":
        raise RegistryStageError("research_artifact_decision_invalid")

    manifest = _load_exact_manifest(
        runtime.repo_root,
        implementation,
        runtime.strategy_id,
    )
    contract_payload = _jsonable(dataclasses.asdict(manifest.contract))
    contract_sha256 = hashlib.sha256(
        json.dumps(
            contract_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    artifact_payload = {
        "schema_version": 1,
        "engine": "REGISTRY",
        "pipeline_run_id": runtime.run_id,
        "strategy_id": runtime.strategy_id,
        "decision": "CANONICAL_STRATEGY_CONTRACT_VERIFIED",
        "module_path": manifest.module_path,
        "implementation_file": str(implementation),
        "implementation_file_sha256": sha256_file(implementation),
        "contract_sha256": contract_sha256,
        "contract": contract_payload,
        "research_result_manifest": str(research_manifest_path),
        "research_result_manifest_file_sha256": sha256_file(research_manifest_path),
        "research_artifact": str(research_artifact),
        "research_artifact_sha256": sha256_file(research_artifact),
        "hypothesis_sha256": research_payload.get("hypothesis_sha256"),
        "allowed_for_live_execution": False,
        "safety": {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
        },
    }
    artifact = runtime.write_json_artifact("registry.stage.json", artifact_payload)
    return runtime.write_success(
        artifact=artifact,
        verdict="CANONICAL_STRATEGY_CONTRACT_VERIFIED",
        metrics=EngineMetrics(strategies_loaded=1),
        limitations=[
            "Registry acceptance proves canonical metadata and file lineage only; implementation truth is evaluated by the next stage."
        ],
    )


def _load_exact_manifest(
    repo_root: Path,
    implementation: Path,
    strategy_id: str,
) -> StrategyManifest:
    relative = implementation.relative_to(repo_root).with_suffix("")
    module_name = ".".join(relative.parts)
    root_text = str(repo_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    importlib.invalidate_caches()
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise RegistryStageError(
            f"strategy_module_import_failed:{module_name}:{type(exc).__name__}:{exc}"
        ) from exc

    unique: dict[int, StrategyContract] = {}
    for value in vars(module).values():
        if isinstance(value, StrategyContract) and value.strategy_id == strategy_id:
            unique[id(value)] = value
    contracts = list(unique.values())
    if not contracts:
        raise RegistryStageError("strategy_contract_not_found_in_declared_file")
    if len(contracts) != 1:
        raise RegistryStageError("duplicate_strategy_contracts_in_declared_file")
    return StrategyManifest(
        contract=contracts[0],
        file_path=str(implementation),
        module_path=module_name,
    )


def _verify_single_upstream_artifact(result: EngineResult) -> Path:
    if len(result.artifacts_generated) != 1:
        raise RegistryStageError("research_result_requires_single_artifact")
    artifact = Path(result.artifacts_generated[0]).resolve()
    expected = result.output_hashes.get(str(artifact))
    if not artifact.is_file() or not expected or sha256_file(artifact) != expected:
        raise RegistryStageError("research_result_artifact_hash_invalid")
    return artifact


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryStageError(f"registry_json_unreadable:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise RegistryStageError(f"registry_json_must_be_object:{path}")
    return payload


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


__all__ = ["RegistryStageError", "run_registry_stage"]

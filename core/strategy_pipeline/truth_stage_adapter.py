from __future__ import annotations

import dataclasses
from datetime import date, datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from core.strategy_pipeline.adapter_runtime import PipelineAdapterRuntime
from core.strategy_pipeline.pipeline_models import EngineResult, EngineType, PipelineState
from core.strategy_pipeline.result_manifest import load_engine_result_manifest, sha256_file
from core.strategy_pipeline.truth_oracle import (
    TruthOracleClassification,
    TruthOracleResult,
    evaluate_truth_oracle,
)
from core.strategy_registry.registry_types import (
    AuditStatus,
    CertificationStatus,
    ImplementationStatus,
    PaperValidationStatus,
    ProductionStatus,
    ReplayStatus,
)
from core.strategy_registry.strategy_contract import StrategyContract
from core.strategy_registry.strategy_manifest import StrategyManifest


class TruthStageError(ValueError):
    """Raised when exact Registry lineage cannot be audited."""


AuditCallable = Callable[
    [StrategyManifest, Path],
    tuple[str, dict[str, Any], list[str]],
]


def run_truth_stage(
    runtime: PipelineAdapterRuntime,
    *,
    auditor: AuditCallable | None = None,
    oracle: Callable[[str, str], TruthOracleResult] = evaluate_truth_oracle,
) -> EngineResult:
    if len(runtime.input_hashes) != 1:
        raise TruthStageError("truth_requires_exactly_one_registry_result_manifest")
    registry_manifest_path = Path(next(iter(runtime.input_hashes))).resolve()
    if registry_manifest_path.name != "registry.result.json":
        raise TruthStageError("truth_upstream_must_be_registry_result_manifest")

    registry_result = load_engine_result_manifest(registry_manifest_path)
    if (
        registry_result.engine != EngineType.REGISTRY
        or registry_result.state != PipelineState.SUCCESS
        or registry_result.strategy_id != runtime.strategy_id
        or registry_result.run_id != runtime.run_id
        or not registry_result.verified
        or registry_result.verdict != "CANONICAL_STRATEGY_CONTRACT_VERIFIED"
    ):
        raise TruthStageError("registry_result_lineage_invalid")

    registry_artifact = _verify_single_upstream_artifact(registry_result)
    registry_payload = _load_json(registry_artifact)
    if registry_payload.get("strategy_id") != runtime.strategy_id:
        raise TruthStageError("registry_artifact_strategy_mismatch")
    if registry_payload.get("pipeline_run_id") != runtime.run_id:
        raise TruthStageError("registry_artifact_run_mismatch")
    if registry_payload.get("decision") != "CANONICAL_STRATEGY_CONTRACT_VERIFIED":
        raise TruthStageError("registry_artifact_decision_invalid")

    implementation = Path(
        str(registry_payload.get("implementation_file") or "")
    ).resolve()
    strategies_root = (runtime.repo_root / "strategies").resolve()
    if not implementation.is_file() or strategies_root not in implementation.parents:
        raise TruthStageError("registry_implementation_path_invalid")
    expected_implementation_hash = str(
        registry_payload.get("implementation_file_sha256") or ""
    )
    if sha256_file(implementation) != expected_implementation_hash:
        raise TruthStageError("implementation_changed_after_registry")

    contract_payload = registry_payload.get("contract")
    if not isinstance(contract_payload, Mapping):
        raise TruthStageError("registry_contract_payload_missing")
    contract_hash = _sha256_json(contract_payload)
    if contract_hash != registry_payload.get("contract_sha256"):
        raise TruthStageError("registry_contract_hash_mismatch")
    contract = _contract_from_payload(contract_payload)
    manifest = StrategyManifest(
        contract=contract,
        file_path=str(implementation),
        module_path=str(registry_payload.get("module_path") or ""),
    )
    if contract.strategy_id != runtime.strategy_id:
        raise TruthStageError("registry_contract_strategy_mismatch")

    source_code = implementation.read_text(encoding="utf-8")
    declared_description = f"{contract.description} {contract.market_hypothesis}"
    oracle_result = oracle(source_code, declared_description)
    audit = auditor or audit_exact_strategy
    implementation_verdict, audit_payload, audit_blockers = audit(
        manifest,
        implementation,
    )

    success = (
        implementation_verdict == "IMPLEMENTATION_VERIFIED"
        and oracle_result.classification == TruthOracleClassification.PASS
        and not audit_blockers
    )
    blockers = list(audit_blockers)
    if oracle_result.classification != TruthOracleClassification.PASS:
        blockers.append(oracle_result.reason)
    blockers = sorted(set(item for item in blockers if item))

    artifact_payload = {
        "schema_version": 1,
        "engine": "TRUTH",
        "pipeline_run_id": runtime.run_id,
        "strategy_id": runtime.strategy_id,
        "decision": (
            "IMPLEMENTATION_VERIFIED"
            if success
            else "IMPLEMENTATION_NOT_VERIFIED"
        ),
        "implementation_verdict": implementation_verdict,
        "implementation_file": str(implementation),
        "implementation_file_sha256": sha256_file(implementation),
        "contract_sha256": contract_hash,
        "registry_result_manifest": str(registry_manifest_path),
        "registry_result_manifest_file_sha256": sha256_file(
            registry_manifest_path
        ),
        "registry_artifact": str(registry_artifact),
        "registry_artifact_sha256": sha256_file(registry_artifact),
        "independent_oracle": _jsonable(oracle_result),
        "audit": audit_payload,
        "blockers": blockers,
        "allowed_for_live_execution": False,
        "safety": {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
        },
    }
    artifact = runtime.write_json_artifact("truth.stage.json", artifact_payload)
    if success:
        return runtime.write_success(
            artifact=artifact,
            verdict="IMPLEMENTATION_VERIFIED",
            limitations=[
                "Truth verification proves declared implementation structure, not profitability or outcome edge."
            ],
        )
    return runtime.write_blocked(
        verdict="IMPLEMENTATION_NOT_VERIFIED",
        blockers=blockers or [implementation_verdict],
        artifact=artifact,
    )


def audit_exact_strategy(
    manifest: StrategyManifest,
    implementation: Path,
) -> tuple[str, dict[str, Any], list[str]]:
    """Run the existing Truth components on exactly one declared implementation."""
    from core.strategy_truth.control_flow import build_control_flow_graph
    from core.strategy_truth.dependency_analyzer import DependencyAnalyzer
    from core.strategy_truth.heuristic_detector import HeuristicDetector
    from core.strategy_truth.implementation_auditor import ImplementationAuditor
    from core.strategy_truth.mathematical_auditor import (
        MathematicalAuditor,
        MathematicalClassification,
    )
    from core.strategy_truth.parameter_auditor import ParameterAuditor
    from core.strategy_truth.rule_extractor import RuleExtractor
    from core.strategy_truth.semantic_comparator import (
        SemanticClassification,
        SemanticComparator,
    )
    from core.strategy_truth.source_scanner import SourceScanner
    from core.strategy_truth.truth_types import ImplementationVerdict

    strategy_id = manifest.contract.strategy_id
    scanner = SourceScanner(strategy_id, str(implementation))
    source_evidence = scanner.scan()
    rule_evidence = RuleExtractor(strategy_id, str(implementation)).extract()
    parameter_findings = ParameterAuditor(str(implementation)).audit()
    heuristic_findings = HeuristicDetector(str(implementation)).audit()
    dependency_findings = DependencyAnalyzer(
        manifest.contract,
        source_evidence,
    ).analyze()
    impl_auditor = ImplementationAuditor(
        manifest.contract,
        source_evidence,
        rule_evidence,
    )
    rule_comparisons = impl_auditor.audit_rules()
    indicator_findings = impl_auditor.audit_indicators()
    cfg = build_control_flow_graph(str(implementation), scanner.source_code)
    declared_description = (
        f"{manifest.contract.description} {manifest.contract.market_hypothesis}"
    )
    semantic_results = SemanticComparator(
        cfg,
        declared_description,
    ).compare()
    mathematical_result = MathematicalAuditor(
        cfg,
        declared_description,
    ).audit()

    verdict = impl_auditor.determine_verdict(rule_comparisons)
    has_heuristic_risk = any(
        "RISK" in item.classification.value for item in heuristic_findings
    )
    has_indicator_gap = any(
        item.status.value != "DECLARED_AND_USED" for item in indicator_findings
    )
    has_dependency_risk = any(
        item.is_missing
        or item.is_unused
        or item.is_circular
        or item.is_direct_coupling
        for item in dependency_findings
    )
    is_semantic_match = bool(semantic_results) and all(
        item.classification == SemanticClassification.SEMANTIC_MATCH
        for item in semantic_results
    )
    is_math_match = (
        mathematical_result.classification
        == MathematicalClassification.MATHEMATICAL_MATCH
    )
    if not cfg.is_reconstructable:
        verdict = ImplementationVerdict.UNABLE_TO_VERIFY
    elif any(
        item.classification
        in {
            SemanticClassification.SEMANTIC_CONTRADICTION,
            SemanticClassification.SEMANTIC_MISMATCH,
        }
        for item in semantic_results
    ):
        verdict = ImplementationVerdict.IMPLEMENTATION_MISMATCH
    elif (
        mathematical_result.classification
        == MathematicalClassification.MATHEMATICAL_MISMATCH
    ):
        verdict = ImplementationVerdict.IMPLEMENTATION_MISMATCH
    elif (
        not is_semantic_match
        or not is_math_match
        or has_heuristic_risk
        or has_indicator_gap
        or has_dependency_risk
    ):
        if verdict in {
            ImplementationVerdict.IMPLEMENTATION_VERIFIED,
            ImplementationVerdict.PARTIALLY_VERIFIED,
        }:
            verdict = ImplementationVerdict.REQUIRES_MANUAL_REVIEW

    blockers = _audit_blockers(
        verdict.value,
        rule_comparisons,
        heuristic_findings,
        indicator_findings,
        dependency_findings,
        semantic_results,
        mathematical_result,
        cfg.is_reconstructable,
    )
    payload = {
        "verdict": verdict.value,
        "source_evidence": _jsonable(source_evidence),
        "rule_evidence": _jsonable(rule_evidence),
        "rule_comparisons": _jsonable(rule_comparisons),
        "parameter_findings": _jsonable(parameter_findings),
        "heuristic_findings": _jsonable(heuristic_findings),
        "indicator_findings": _jsonable(indicator_findings),
        "dependency_findings": _jsonable(dependency_findings),
        "cfg_is_reconstructable": cfg.is_reconstructable,
        "semantic_results": _jsonable(semantic_results),
        "mathematical_result": _jsonable(mathematical_result),
    }
    return verdict.value, payload, blockers


def _audit_blockers(
    verdict: str,
    rules: list[Any],
    heuristics: list[Any],
    indicators: list[Any],
    dependencies: list[Any],
    semantics: list[Any],
    mathematical: Any,
    reconstructable: bool,
) -> list[str]:
    blockers = [] if verdict == "IMPLEMENTATION_VERIFIED" else [verdict]
    if not reconstructable:
        blockers.append("control_flow_not_reconstructable")
    blockers.extend(
        f"rule:{item.registry_field}:{item.status.value}"
        for item in rules
        if item.status.value != "MATCH"
    )
    blockers.extend(
        f"heuristic:{item.classification.value}:{item.keyword_found}"
        for item in heuristics
        if "RISK" in item.classification.value
        or item.classification.value == "UNKNOWN"
    )
    blockers.extend(
        f"indicator:{item.indicator_name}:{item.status.value}"
        for item in indicators
        if item.status.value != "DECLARED_AND_USED"
    )
    blockers.extend(
        f"dependency:{item.dependency_name}:{item.reason}"
        for item in dependencies
        if item.is_missing
        or item.is_unused
        or item.is_circular
        or item.is_direct_coupling
    )
    blockers.extend(
        f"semantic:{item.classification.value}:{item.reason}"
        for item in semantics
        if item.classification.value != "SEMANTIC_MATCH"
    )
    if mathematical.classification.value != "MATHEMATICAL_MATCH":
        blockers.append(
            f"mathematical:{mathematical.classification.value}:{mathematical.reason}"
        )
    return sorted(set(blockers))


def _contract_from_payload(payload: Mapping[str, Any]) -> StrategyContract:
    values = dict(payload)
    try:
        values["created_date"] = date.fromisoformat(str(values["created_date"]))
        values["implementation_status"] = ImplementationStatus[
            str(values["implementation_status"])
        ]
        values["audit_status"] = AuditStatus[str(values["audit_status"])]
        values["replay_status"] = ReplayStatus[str(values["replay_status"])]
        values["certification_status"] = CertificationStatus[
            str(values["certification_status"])
        ]
        values["paper_validation_status"] = PaperValidationStatus[
            str(values["paper_validation_status"])
        ]
        values["production_status"] = ProductionStatus[
            str(values["production_status"])
        ]
        return StrategyContract(**values)
    except (KeyError, TypeError, ValueError) as exc:
        raise TruthStageError(
            f"registry_contract_deserialization_failed:{exc}"
        ) from exc


def _verify_single_upstream_artifact(result: EngineResult) -> Path:
    if len(result.artifacts_generated) != 1:
        raise TruthStageError("registry_result_requires_single_artifact")
    artifact = Path(result.artifacts_generated[0]).resolve()
    expected = result.output_hashes.get(str(artifact))
    if not artifact.is_file() or not expected or sha256_file(artifact) != expected:
        raise TruthStageError("registry_result_artifact_hash_invalid")
    return artifact


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TruthStageError(f"truth_json_unreadable:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise TruthStageError(f"truth_json_must_be_object:{path}")
    return payload


def _sha256_json(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


__all__ = [
    "TruthStageError",
    "audit_exact_strategy",
    "run_truth_stage",
]

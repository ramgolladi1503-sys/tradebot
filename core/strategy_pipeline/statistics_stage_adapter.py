from __future__ import annotations

from datetime import date
import json
import math
from pathlib import Path
import random
from typing import Any, Mapping, Sequence

from core.strategy_pipeline.adapter_runtime import PipelineAdapterRuntime
from core.strategy_pipeline.pipeline_models import EngineResult, EngineType, PipelineState
from core.strategy_pipeline.result_manifest import load_engine_result_manifest, sha256_file


class StatisticsStageError(ValueError):
    """Raised when statistical evidence is incomplete, non-causal, or untraceable."""


_REQUIRED_CONFIG_FIELDS = {
    "schema_version",
    "source_as_of",
    "min_total_sample",
    "min_development_sample",
    "min_holdout_sample",
    "min_net_expectancy",
    "min_profit_factor",
    "max_drawdown_abs",
    "bootstrap_iterations",
    "bootstrap_seed",
    "bootstrap_confidence",
    "min_bootstrap_lower_bound",
    "null_iterations",
    "max_null_pvalue",
    "wfa_folds",
    "min_wfa_profitable_fold_ratio",
    "cost_sensitivity_multipliers",
    "min_worst_cost_expectancy",
}


def run_statistics_stage(
    runtime: PipelineAdapterRuntime,
    *,
    validation_config_file: str | Path,
) -> EngineResult:
    config_path = Path(validation_config_file).expanduser().resolve()
    supplied = set(runtime.input_hashes)
    if str(config_path) not in supplied:
        raise StatisticsStageError("validation_config_not_declared_as_input")
    upstream = supplied - {str(config_path)}
    if len(upstream) != 1:
        raise StatisticsStageError(
            "statistics_requires_outcomes_manifest_and_validation_config"
        )
    outcomes_manifest_path = Path(next(iter(upstream))).resolve()
    if outcomes_manifest_path.name != "outcomes.result.json":
        raise StatisticsStageError(
            "statistics_upstream_must_be_outcomes_result_manifest"
        )

    outcomes_artifact, outcomes_payload = _verify_outcomes_lineage(
        runtime,
        outcomes_manifest_path,
    )
    config = _load_validation_config(config_path)
    research_payload = _load_research_lineage(runtime, outcomes_payload)
    candidate_path = Path(str(outcomes_payload.get("candidate_file") or "")).resolve()
    expected_candidate_hash = str(outcomes_payload.get("candidate_file_sha256") or "")
    if not candidate_path.is_file() or sha256_file(candidate_path) != expected_candidate_hash:
        raise StatisticsStageError("candidate_file_changed_after_outcomes")

    candidate_metadata = _load_candidate_metadata(candidate_path, runtime.strategy_id)
    records = _load_complete_records(outcomes_payload, candidate_metadata)
    windows = _research_windows(research_payload)
    _validate_partitions(records, windows)

    evaluation = evaluate_statistics(records, config)
    blockers = [name for name, passed in evaluation["gates"].items() if not passed]
    decision = (
        "STATISTICAL_VALIDATION_VERIFIED"
        if not blockers
        else "STATISTICAL_VALIDATION_FAILED"
    )
    artifact_payload = {
        "schema_version": 1,
        "engine": "STATISTICS",
        "pipeline_run_id": runtime.run_id,
        "strategy_id": runtime.strategy_id,
        "decision": decision,
        "outcomes_result_manifest": str(outcomes_manifest_path),
        "outcomes_result_manifest_file_sha256": sha256_file(outcomes_manifest_path),
        "outcomes_artifact": str(outcomes_artifact),
        "outcomes_artifact_sha256": sha256_file(outcomes_artifact),
        "candidate_file": str(candidate_path),
        "candidate_file_sha256": sha256_file(candidate_path),
        "validation_config_file": str(config_path),
        "validation_config_file_sha256": sha256_file(config_path),
        "validation_config": config,
        "research_windows": windows,
        "evaluation": evaluation,
        "blockers": blockers,
        "allowed_for_live_execution": False,
        "safety": {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
        },
    }
    artifact = runtime.write_json_artifact("statistics.stage.json", artifact_payload)
    if blockers:
        return runtime.write_blocked(
            verdict="STATISTICAL_VALIDATION_FAILED",
            blockers=blockers,
            artifact=artifact,
        )
    return runtime.write_success(
        artifact=artifact,
        verdict="STATISTICAL_VALIDATION_VERIFIED",
        limitations=[
            "Statistical validation is conditional on the frozen data, replay, costs, and configured thresholds."
        ],
    )


def evaluate_statistics(
    records: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    development = sorted(
        (dict(row) for row in records if row["sample_partition"] == "DEVELOPMENT"),
        key=lambda row: (row["session_date"], row["candidate_id"]),
    )
    holdout = sorted(
        (dict(row) for row in records if row["sample_partition"] == "HOLDOUT"),
        key=lambda row: (row["session_date"], row["candidate_id"]),
    )
    all_records = development + holdout
    development_metrics = _metrics([float(row["net_pnl"]) for row in development])
    holdout_metrics = _metrics([float(row["net_pnl"]) for row in holdout])
    total_metrics = _metrics([float(row["net_pnl"]) for row in all_records])
    bootstrap = _bootstrap_mean(
        [float(row["net_pnl"]) for row in development],
        iterations=int(config["bootstrap_iterations"]),
        seed=int(config["bootstrap_seed"]),
        confidence=float(config["bootstrap_confidence"]),
    )
    null_control = _sign_randomization_test(
        [float(row["net_pnl"]) for row in development],
        iterations=int(config["null_iterations"]),
        seed=int(config["bootstrap_seed"]) + 1,
    )
    direction_flip = {
        "base_expectancy": development_metrics["expectancy"],
        "flipped_expectancy": -development_metrics["expectancy"],
        "passed": development_metrics["expectancy"] > -development_metrics["expectancy"],
    }
    wfa = _walk_forward(development, folds=int(config["wfa_folds"]))
    cost_sensitivity = _cost_sensitivity(
        all_records,
        multipliers=[float(value) for value in config["cost_sensitivity_multipliers"]],
    )
    gates = {
        "minimum_total_sample": len(all_records) >= int(config["min_total_sample"]),
        "minimum_development_sample": len(development)
        >= int(config["min_development_sample"]),
        "minimum_holdout_sample": len(holdout) >= int(config["min_holdout_sample"]),
        "development_expectancy": development_metrics["expectancy"]
        >= float(config["min_net_expectancy"]),
        "development_profit_factor": development_metrics["profit_factor"]
        >= float(config["min_profit_factor"]),
        "holdout_expectancy": holdout_metrics["expectancy"]
        >= float(config["min_net_expectancy"]),
        "holdout_profit_factor": holdout_metrics["profit_factor"]
        >= float(config["min_profit_factor"]),
        "drawdown_limit": abs(total_metrics["max_drawdown"])
        <= float(config["max_drawdown_abs"]),
        "bootstrap_lower_bound": bootstrap["lower_bound"]
        >= float(config["min_bootstrap_lower_bound"]),
        "sign_randomization_control": null_control["pvalue"]
        <= float(config["max_null_pvalue"]),
        "direction_flip_control": direction_flip["passed"],
        "walk_forward_stability": wfa["profitable_fold_ratio"]
        >= float(config["min_wfa_profitable_fold_ratio"]),
        "cost_sensitivity": cost_sensitivity["worst_expectancy"]
        >= float(config["min_worst_cost_expectancy"]),
    }
    return {
        "sample_counts": {
            "total": len(all_records),
            "development": len(development),
            "holdout": len(holdout),
        },
        "development": development_metrics,
        "holdout": holdout_metrics,
        "total": total_metrics,
        "bootstrap": bootstrap,
        "negative_controls": {
            "sign_randomization": null_control,
            "direction_flip": direction_flip,
        },
        "walk_forward": wfa,
        "cost_sensitivity": cost_sensitivity,
        "gates": gates,
    }


def _verify_outcomes_lineage(
    runtime: PipelineAdapterRuntime,
    manifest_path: Path,
) -> tuple[Path, dict[str, Any]]:
    result = load_engine_result_manifest(manifest_path)
    if (
        result.engine != EngineType.OUTCOMES
        or result.state != PipelineState.SUCCESS
        or result.strategy_id != runtime.strategy_id
        or result.run_id != runtime.run_id
        or result.verdict != "CAUSAL_OUTCOME_EVIDENCE_VERIFIED"
        or not result.verified
    ):
        raise StatisticsStageError("outcomes_result_lineage_invalid")
    artifact = _single_verified_artifact(result, "outcomes")
    payload = _load_json_object(artifact)
    if (
        payload.get("strategy_id") != runtime.strategy_id
        or payload.get("pipeline_run_id") != runtime.run_id
        or payload.get("decision") != "CAUSAL_OUTCOME_EVIDENCE_VERIFIED"
    ):
        raise StatisticsStageError("outcomes_artifact_decision_invalid")
    causal = payload.get("causal_contract")
    if not isinstance(causal, Mapping) or not all(
        causal.get(field) is True
        for field in (
            "completed_bar_required",
            "execution_eligible_after_signal",
            "same_timestamp_signal_entry_forbidden",
            "ltp_fallback_forbidden",
            "spread_double_count_forbidden",
        )
    ):
        raise StatisticsStageError("outcomes_causal_contract_incomplete")
    return artifact, payload


def _load_research_lineage(
    runtime: PipelineAdapterRuntime,
    outcomes_payload: Mapping[str, Any],
) -> dict[str, Any]:
    truth_manifest = Path(str(outcomes_payload.get("truth_result_manifest") or "")).resolve()
    truth_result = load_engine_result_manifest(truth_manifest)
    _require_same_lineage(runtime, truth_result, EngineType.TRUTH, "IMPLEMENTATION_VERIFIED")
    truth_payload = _load_json_object(_single_verified_artifact(truth_result, "truth"))
    registry_manifest = Path(str(truth_payload.get("registry_result_manifest") or "")).resolve()
    registry_result = load_engine_result_manifest(registry_manifest)
    _require_same_lineage(
        runtime,
        registry_result,
        EngineType.REGISTRY,
        "CANONICAL_STRATEGY_CONTRACT_VERIFIED",
    )
    registry_payload = _load_json_object(
        _single_verified_artifact(registry_result, "registry")
    )
    research_manifest = Path(
        str(registry_payload.get("research_result_manifest") or "")
    ).resolve()
    research_result = load_engine_result_manifest(research_manifest)
    _require_same_lineage(
        runtime,
        research_result,
        EngineType.RESEARCH,
        "FROZEN_HYPOTHESIS_VERIFIED",
    )
    research_payload = _load_json_object(
        _single_verified_artifact(research_result, "research")
    )
    if research_payload.get("allowed_for_live_execution") is not False:
        raise StatisticsStageError("research_lineage_live_authority_invalid")
    return research_payload


def _require_same_lineage(
    runtime: PipelineAdapterRuntime,
    result: EngineResult,
    engine: EngineType,
    verdict: str,
) -> None:
    if (
        result.engine != engine
        or result.state != PipelineState.SUCCESS
        or result.strategy_id != runtime.strategy_id
        or result.run_id != runtime.run_id
        or result.verdict != verdict
        or not result.verified
    ):
        raise StatisticsStageError(f"{engine.value.lower()}_lineage_invalid")


def _single_verified_artifact(result: EngineResult, label: str) -> Path:
    if len(result.artifacts_generated) != 1:
        raise StatisticsStageError(f"{label}_result_requires_single_artifact")
    artifact = Path(result.artifacts_generated[0]).resolve()
    expected = result.output_hashes.get(str(artifact))
    if not artifact.is_file() or not expected or sha256_file(artifact) != expected:
        raise StatisticsStageError(f"{label}_artifact_hash_invalid")
    return artifact


def _load_candidate_metadata(
    path: Path,
    strategy_id: str,
) -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StatisticsStageError(
                f"candidate_json_invalid:{line_number}:{exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise StatisticsStageError(f"candidate_row_not_object:{line_number}")
        candidate_id = str(payload.get("candidate_id") or "").strip()
        if not candidate_id or candidate_id in metadata:
            raise StatisticsStageError(f"candidate_id_invalid_or_duplicate:{line_number}")
        if str(payload.get("strategy_id")) != strategy_id:
            raise StatisticsStageError(f"candidate_strategy_mismatch:{candidate_id}")
        partition = str(payload.get("sample_partition") or "").upper()
        if partition not in {"DEVELOPMENT", "HOLDOUT"}:
            raise StatisticsStageError(
                f"candidate_partition_invalid:{candidate_id}:{partition or 'missing'}"
            )
        session_date = str(payload.get("session_date") or "").strip()
        try:
            date.fromisoformat(session_date)
        except ValueError as exc:
            raise StatisticsStageError(
                f"candidate_session_date_invalid:{candidate_id}:{session_date or 'missing'}"
            ) from exc
        metadata[candidate_id] = {
            "sample_partition": partition,
            "session_date": session_date,
            "regime": str(payload.get("regime") or "UNKNOWN"),
        }
    return metadata


def _load_complete_records(
    outcomes_payload: Mapping[str, Any],
    metadata: Mapping[str, Mapping[str, str]],
) -> list[dict[str, Any]]:
    raw_records = outcomes_payload.get("records")
    if not isinstance(raw_records, list):
        raise StatisticsStageError("outcomes_records_missing")
    records: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, Mapping) or raw.get("status") != "COMPLETE":
            continue
        candidate_id = str(raw.get("candidate_id") or "")
        meta = metadata.get(candidate_id)
        if meta is None:
            raise StatisticsStageError(
                f"outcomes_candidate_metadata_missing:{candidate_id or index}"
            )
        costs = raw.get("costs")
        if not isinstance(costs, Mapping):
            raise StatisticsStageError(f"outcomes_costs_missing:{candidate_id}")
        gross = _finite_float(raw.get("gross_pnl"), "gross_pnl")
        net = _finite_float(raw.get("net_pnl"), "net_pnl")
        total_cost = _finite_float(costs.get("total_cost"), "total_cost")
        if not math.isclose(gross - total_cost, net, rel_tol=1e-9, abs_tol=1e-8):
            raise StatisticsStageError(f"outcomes_net_pnl_reconciliation_failed:{candidate_id}")
        records.append(
            {
                "candidate_id": candidate_id,
                "net_pnl": net,
                "gross_pnl": gross,
                "total_cost": total_cost,
                **dict(meta),
            }
        )
    if not records:
        raise StatisticsStageError("no_complete_outcome_records")
    return records


def _research_windows(payload: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    return {
        "development": _parse_window(payload.get("development_window"), "development"),
        "holdout": _parse_window(payload.get("holdout_window"), "holdout"),
    }


def _parse_window(value: Any, label: str) -> dict[str, str]:
    text = str(value or "")
    parts = text.split("/")
    if len(parts) != 2:
        raise StatisticsStageError(f"research_{label}_window_invalid")
    start, end = (date.fromisoformat(part) for part in parts)
    if start > end:
        raise StatisticsStageError(f"research_{label}_window_reversed")
    return {"start": start.isoformat(), "end": end.isoformat()}


def _validate_partitions(
    records: Sequence[Mapping[str, Any]],
    windows: Mapping[str, Mapping[str, str]],
) -> None:
    development_dates: set[str] = set()
    holdout_dates: set[str] = set()
    for row in records:
        partition = str(row["sample_partition"])
        session_date = str(row["session_date"])
        window = windows[partition.lower()]
        if not (window["start"] <= session_date <= window["end"]):
            raise StatisticsStageError(
                f"{partition.lower()}_date_outside_frozen_window:{session_date}"
            )
        (development_dates if partition == "DEVELOPMENT" else holdout_dates).add(
            session_date
        )
    overlap = development_dates & holdout_dates
    if overlap:
        raise StatisticsStageError(
            "development_holdout_date_overlap:" + ",".join(sorted(overlap))
        )


def _metrics(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {
            "count": 0,
            "expectancy": float("-inf"),
            "profit_factor": 0.0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "max_drawdown": float("-inf"),
        }
    wins = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    profit_factor = wins / losses if losses > 0 else (float("inf") if wins > 0 else 0.0)
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return {
        "count": len(values),
        "expectancy": sum(values) / len(values),
        "profit_factor": profit_factor,
        "win_rate": sum(value > 0 for value in values) / len(values),
        "total_pnl": sum(values),
        "max_drawdown": max_drawdown,
    }


def _bootstrap_mean(
    values: Sequence[float],
    *,
    iterations: int,
    seed: int,
    confidence: float,
) -> dict[str, float]:
    if not values or iterations < 100 or not 0.5 < confidence < 1.0:
        raise StatisticsStageError("bootstrap_configuration_invalid")
    rng = random.Random(seed)
    means = sorted(
        sum(rng.choice(values) for _ in values) / len(values)
        for _ in range(iterations)
    )
    alpha = (1.0 - confidence) / 2.0
    lower_index = max(0, min(iterations - 1, int(alpha * iterations)))
    upper_index = max(0, min(iterations - 1, int((1.0 - alpha) * iterations) - 1))
    return {
        "iterations": iterations,
        "seed": seed,
        "confidence": confidence,
        "lower_bound": means[lower_index],
        "upper_bound": means[upper_index],
        "median": means[iterations // 2],
    }


def _sign_randomization_test(
    values: Sequence[float],
    *,
    iterations: int,
    seed: int,
) -> dict[str, float]:
    if not values or iterations < 100:
        raise StatisticsStageError("null_control_configuration_invalid")
    observed = sum(values) / len(values)
    magnitudes = [abs(value) for value in values]
    rng = random.Random(seed)
    exceedances = 0
    for _ in range(iterations):
        null_mean = sum(
            magnitude if rng.random() >= 0.5 else -magnitude
            for magnitude in magnitudes
        ) / len(magnitudes)
        if null_mean >= observed:
            exceedances += 1
    return {
        "iterations": iterations,
        "seed": seed,
        "observed_expectancy": observed,
        "pvalue": (exceedances + 1) / (iterations + 1),
    }


def _walk_forward(
    development: Sequence[Mapping[str, Any]],
    *,
    folds: int,
) -> dict[str, Any]:
    if folds < 2 or len(development) < folds:
        raise StatisticsStageError("walk_forward_configuration_invalid")
    sizes = [len(development) // folds] * folds
    for index in range(len(development) % folds):
        sizes[index] += 1
    reports: list[dict[str, Any]] = []
    offset = 0
    for fold_index, size in enumerate(sizes, 1):
        fold = development[offset : offset + size]
        offset += size
        metrics = _metrics([float(row["net_pnl"]) for row in fold])
        reports.append(
            {
                "fold": fold_index,
                "start_date": fold[0]["session_date"],
                "end_date": fold[-1]["session_date"],
                **metrics,
                "profitable": metrics["expectancy"] > 0,
            }
        )
    return {
        "folds": reports,
        "profitable_fold_ratio": sum(report["profitable"] for report in reports)
        / len(reports),
    }


def _cost_sensitivity(
    records: Sequence[Mapping[str, Any]],
    *,
    multipliers: Sequence[float],
) -> dict[str, Any]:
    if not multipliers or any(multiplier < 1.0 for multiplier in multipliers):
        raise StatisticsStageError("cost_sensitivity_multipliers_invalid")
    scenarios: list[dict[str, float]] = []
    for multiplier in sorted(set(multipliers)):
        values = [
            float(row["gross_pnl"]) - multiplier * float(row["total_cost"])
            for row in records
        ]
        metrics = _metrics(values)
        scenarios.append(
            {
                "multiplier": multiplier,
                "expectancy": metrics["expectancy"],
                "profit_factor": metrics["profit_factor"],
                "total_pnl": metrics["total_pnl"],
            }
        )
    return {
        "scenarios": scenarios,
        "worst_expectancy": min(scenario["expectancy"] for scenario in scenarios),
    }


def _load_validation_config(path: Path) -> dict[str, Any]:
    payload = _load_json_object(path)
    missing = sorted(_REQUIRED_CONFIG_FIELDS - set(payload))
    if missing:
        raise StatisticsStageError(
            "validation_config_missing_fields:" + ",".join(missing)
        )
    if payload["schema_version"] != 1 or not str(payload["source_as_of"]).strip():
        raise StatisticsStageError("validation_config_identity_invalid")
    config = dict(payload)
    integer_fields = {
        "min_total_sample",
        "min_development_sample",
        "min_holdout_sample",
        "bootstrap_iterations",
        "bootstrap_seed",
        "null_iterations",
        "wfa_folds",
    }
    for field in integer_fields:
        config[field] = int(config[field])
    float_fields = _REQUIRED_CONFIG_FIELDS - integer_fields - {
        "schema_version",
        "source_as_of",
        "cost_sensitivity_multipliers",
    }
    for field in float_fields:
        config[field] = float(config[field])
    if not isinstance(config["cost_sensitivity_multipliers"], list):
        raise StatisticsStageError("cost_sensitivity_multipliers_must_be_list")
    config["cost_sensitivity_multipliers"] = [
        float(value) for value in config["cost_sensitivity_multipliers"]
    ]
    if any(config[field] < 0 for field in integer_fields if field != "bootstrap_seed"):
        raise StatisticsStageError("validation_config_negative_integer")
    return config


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StatisticsStageError(f"json_object_unreadable:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise StatisticsStageError(f"json_object_required:{path}")
    return payload


def _finite_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise StatisticsStageError(f"numeric_field_invalid:{field}") from exc
    if not math.isfinite(number):
        raise StatisticsStageError(f"numeric_field_non_finite:{field}")
    return number


__all__ = [
    "StatisticsStageError",
    "evaluate_statistics",
    "run_statistics_stage",
]

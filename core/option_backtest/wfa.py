from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .engine import OptionBacktestEngine
from .models import OptionBacktestConfig


def _normalize_for_json(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "value") and hasattr(value, "__class__") and value.__class__.__name__.endswith("Enum"):
        return str(value.value)
    if isinstance(value, dict):
        return {str(k): _normalize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_for_json(v) for v in value]
    return value


def _to_timestamp(value: str, timezone: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize(timezone) if ts.tzinfo is None else ts.tz_convert(timezone)


def _profit_factor_metric(summary: dict[str, Any]) -> float | None:
    value = summary.get("profit_factor")
    if value is not None:
        return float(value)
    if summary.get("profit_factor_unbounded") and float(summary.get("wins", 0)) > 0:
        return float("inf")
    return None


def _contamination_count(summary: dict[str, Any]) -> int:
    diagnostics = dict(summary.get("diagnostics") or {})
    return int(
        diagnostics.get("fallback_rows", 0)
        + diagnostics.get("derived_geometry_rows", 0)
        + diagnostics.get("derived_timing_rows", 0)
        + diagnostics.get("proxy_exit_mark_rows", 0)
        + diagnostics.get("strict_exit_quote_rejections", 0)
    )


@dataclass(frozen=True)
class OptionReplayWFARange:
    start: str
    end: str


@dataclass(frozen=True)
class OptionReplayWFAGates:
    min_trades: int = 1
    min_net_expectancy: float = 0.0
    min_profit_factor: float = 1.0
    max_drawdown: float = 999999.0
    max_ambiguity_count: int = 0
    max_contamination_count: int = 0
    min_positive_partition_fraction: float = 1.0
    required_result_label: str = "CERTIFICATION_CANDIDATE"
    require_known_setup_regime_oos: bool = True

    def __post_init__(self):
        if self.min_trades < 0:
            raise ValueError("min_trades_must_be_nonnegative")
        if not 0.0 <= float(self.min_positive_partition_fraction) <= 1.0:
            raise ValueError("min_positive_partition_fraction_out_of_range")


@dataclass(frozen=True)
class OptionReplayWFAConfig:
    base_config: OptionBacktestConfig
    train_range: OptionReplayWFARange
    validation_range: OptionReplayWFARange
    holdout_range: OptionReplayWFARange
    gates: OptionReplayWFAGates = field(default_factory=OptionReplayWFAGates)
    max_feature_lookback_minutes: int = 0
    purge_minutes: int = 0
    embargo_minutes: int = 0
    output_dir: Path | None = None
    frozen_parameters: dict[str, Any] = field(default_factory=dict)
    allow_repeated_holdout_runs: bool = False

    def __post_init__(self):
        if self.base_config.research_mode.value != "REAL_EXECUTABLE_RESEARCH":
            raise ValueError("wfa_requires_real_executable_research_mode")
        if self.max_feature_lookback_minutes < 0 or self.purge_minutes < 0 or self.embargo_minutes < 0:
            raise ValueError("wfa_buffer_minutes_must_be_nonnegative")


def build_wfa_partition_plan(cfg: OptionReplayWFAConfig) -> dict[str, Any]:
    timezone = cfg.base_config.timezone
    train_start = _to_timestamp(cfg.train_range.start, timezone)
    train_end = _to_timestamp(cfg.train_range.end, timezone)
    validation_start = _to_timestamp(cfg.validation_range.start, timezone)
    validation_end = _to_timestamp(cfg.validation_range.end, timezone)
    holdout_start = _to_timestamp(cfg.holdout_range.start, timezone)
    holdout_end = _to_timestamp(cfg.holdout_range.end, timezone)
    if not (train_start <= train_end < validation_start <= validation_end < holdout_start <= holdout_end):
        raise ValueError("non_chronological_or_overlapping_partitions")

    boundary_minutes = max(
        int(cfg.max_feature_lookback_minutes) + int(cfg.base_config.max_hold_minutes),
        int(cfg.purge_minutes),
        int(cfg.embargo_minutes),
    )
    boundary_delta = pd.Timedelta(minutes=boundary_minutes)

    effective = {
        "train": {
            "raw_start": train_start,
            "raw_end": train_end,
            "effective_start": train_start,
            "effective_end": min(train_end, validation_start - boundary_delta),
        },
        "validation": {
            "raw_start": validation_start,
            "raw_end": validation_end,
            "effective_start": max(validation_start, train_end + boundary_delta),
            "effective_end": min(validation_end, holdout_start - boundary_delta),
        },
        "holdout": {
            "raw_start": holdout_start,
            "raw_end": holdout_end,
            "effective_start": max(holdout_start, validation_end + boundary_delta),
            "effective_end": holdout_end,
        },
    }
    for partition_name, partition in effective.items():
        if partition["effective_start"] > partition["effective_end"]:
            raise ValueError(f"empty_effective_partition:{partition_name}")
    return {
        "timezone": timezone,
        "effective_boundary_minutes": boundary_minutes,
        "partitions": {
            name: {
                "raw_start": partition["raw_start"].isoformat(),
                "raw_end": partition["raw_end"].isoformat(),
                "effective_start": partition["effective_start"].isoformat(),
                "effective_end": partition["effective_end"].isoformat(),
            }
            for name, partition in effective.items()
        },
    }


def _frozen_config_hash(cfg: OptionReplayWFAConfig, partition_plan: dict[str, Any]) -> str:
    payload = {
        "base_config": _normalize_for_json(asdict(cfg.base_config)),
        "gates": _normalize_for_json(asdict(cfg.gates)),
        "frozen_parameters": _normalize_for_json(cfg.frozen_parameters),
        "partitions": partition_plan,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _partition_output_dir(base_dir: Path | None, partition_name: str) -> Path | None:
    if base_dir is None:
        return None
    return base_dir / partition_name


def _run_partition(
    *,
    cfg: OptionReplayWFAConfig,
    partition_name: str,
    partition_plan: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    partition = partition_plan["partitions"][partition_name]
    partition_cfg = replace(
        cfg.base_config,
        date_from=partition["effective_start"],
        date_to=partition["effective_end"],
        output_dir=_partition_output_dir(cfg.output_dir, partition_name),
        fill_model_run_id=f"{cfg.base_config.fill_model_run_id}:{run_id}:{partition_name}",
    )
    engine_result = OptionBacktestEngine(partition_cfg).run()
    summary = dict(engine_result.summary)
    return {
        "status": "completed",
        "engine": "OptionBacktestEngine",
        "engine_module": "core.option_backtest.engine.OptionBacktestEngine",
        "raw_range": {
            "start": partition["raw_start"],
            "end": partition["raw_end"],
        },
        "effective_range": {
            "start": partition["effective_start"],
            "end": partition["effective_end"],
        },
        "metrics": {
            "signals_total": int(summary.get("signals_total", 0)),
            "trades_taken": int(summary.get("trades_taken", 0)),
            "after_cost_expectancy": summary.get("after_cost_expectancy"),
            "profit_factor": _profit_factor_metric(summary),
            "max_drawdown": summary.get("max_drawdown"),
            "ambiguity_count": int(summary.get("ambiguity_count", 0)),
            "contamination_count": _contamination_count(summary),
            "result_label": summary.get("result_label"),
            "certifiable": bool(summary.get("certifiable")),
            "net_pnl_value": summary.get("net_pnl_value"),
        },
        "setup_breakdown": summary.get("setup_breakdown", {}),
        "regime_breakdown": summary.get("regime_breakdown", {}),
        "certification_blockers": list(summary.get("certification_blockers") or []),
        "summary": summary,
    }


def _gate_result(name: str, actual: Any, threshold: Any, passed: bool, missing: bool = False) -> dict[str, Any]:
    return {
        "gate": name,
        "actual": actual,
        "threshold": threshold,
        "passed": bool(passed),
        "missing": bool(missing),
    }


def _evaluate_partition_gates(partition_result: dict[str, Any], gates: OptionReplayWFAGates) -> tuple[list[dict[str, Any]], bool]:
    metrics = dict(partition_result.get("metrics") or {})
    summary = dict(partition_result.get("summary") or {})
    gate_rows: list[dict[str, Any]] = []

    trades = metrics.get("trades_taken")
    gate_rows.append(_gate_result("min_trades", trades, gates.min_trades, trades is not None and int(trades) >= int(gates.min_trades), trades is None))

    expectancy = metrics.get("after_cost_expectancy")
    gate_rows.append(
        _gate_result(
            "min_net_expectancy",
            expectancy,
            gates.min_net_expectancy,
            expectancy is not None and float(expectancy) >= float(gates.min_net_expectancy),
            expectancy is None,
        )
    )

    profit_factor = metrics.get("profit_factor")
    gate_rows.append(
        _gate_result(
            "min_profit_factor",
            profit_factor,
            gates.min_profit_factor,
            profit_factor is not None and float(profit_factor) >= float(gates.min_profit_factor),
            profit_factor is None,
        )
    )

    drawdown = metrics.get("max_drawdown")
    gate_rows.append(
        _gate_result(
            "max_drawdown",
            drawdown,
            gates.max_drawdown,
            drawdown is not None and float(drawdown) <= float(gates.max_drawdown),
            drawdown is None,
        )
    )

    ambiguity = metrics.get("ambiguity_count")
    gate_rows.append(
        _gate_result(
            "max_ambiguity_count",
            ambiguity,
            gates.max_ambiguity_count,
            ambiguity is not None and int(ambiguity) <= int(gates.max_ambiguity_count),
            ambiguity is None,
        )
    )

    contamination = metrics.get("contamination_count")
    gate_rows.append(
        _gate_result(
            "max_contamination_count",
            contamination,
            gates.max_contamination_count,
            contamination is not None and int(contamination) <= int(gates.max_contamination_count),
            contamination is None,
        )
    )

    result_label = metrics.get("result_label")
    gate_rows.append(
        _gate_result(
            "required_result_label",
            result_label,
            gates.required_result_label,
            result_label == gates.required_result_label,
            result_label is None,
        )
    )

    if gates.require_known_setup_regime_oos:
        blockers = set(partition_result.get("certification_blockers") or [])
        missing_known_metadata = any(
            blocker in blockers
            for blocker in (
                "missing_setup_id_column",
                "missing_regime_column",
                "missing_oos_label_column",
                "unknown_setup_id",
                "unknown_regime",
                "unknown_oos_label",
            )
        )
        gate_rows.append(
            _gate_result(
                "require_known_setup_regime_oos",
                not missing_known_metadata,
                True,
                not missing_known_metadata,
                False,
            )
        )

    if bool(summary.get("certifiable")) is False:
        gate_rows.append(_gate_result("engine_certifiable", False, True, False, False))
    else:
        gate_rows.append(_gate_result("engine_certifiable", True, True, True, False))

    passed = all(row["passed"] and not row["missing"] for row in gate_rows)
    return gate_rows, passed


def _positive_partition_fraction(partition_results: dict[str, dict[str, Any]]) -> float:
    considered = [partition_results[name] for name in ("validation", "holdout") if partition_results.get(name, {}).get("status") == "completed"]
    if not considered:
        return 0.0
    positives = [
        result
        for result in considered
        if float(result.get("metrics", {}).get("net_pnl_value") or 0.0) > 0.0
    ]
    return float(len(positives)) / float(len(considered))


def _registry_path(output_dir: Path) -> Path:
    return output_dir / "holdout_registry.json"


def _load_holdout_registry(output_dir: Path) -> list[dict[str, Any]]:
    path = _registry_path(output_dir)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def _write_holdout_registry(output_dir: Path, entries: list[dict[str, Any]]) -> None:
    path = _registry_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, sort_keys=True), encoding="utf-8")


def _write_wfa_report(output_dir: Path | None, report: dict[str, Any]) -> None:
    if output_dir is None:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "option_replay_wfa_report.json").write_text(
        json.dumps(_normalize_for_json(report), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_option_replay_wfa(cfg: OptionReplayWFAConfig) -> dict[str, Any]:
    partition_plan = build_wfa_partition_plan(cfg)
    config_hash = _frozen_config_hash(cfg, partition_plan)
    run_id = config_hash[:12]
    report: dict[str, Any] = {
        "engine": "OptionBacktestEngine",
        "engine_module": "core.option_backtest.engine.OptionBacktestEngine",
        "partition_plan": partition_plan,
        "frozen_config": {
            "base_config": _normalize_for_json(asdict(cfg.base_config)),
            "frozen_parameters": _normalize_for_json(cfg.frozen_parameters),
        },
        "acceptance_thresholds": _normalize_for_json(asdict(cfg.gates)),
        "frozen_config_hash": config_hash,
        "run_id": run_id,
        "verdict": "BLOCKED",
        "partitions": {},
        "gates": {},
        "holdout_tracking": {
            "output_dir": str(cfg.output_dir) if cfg.output_dir is not None else None,
            "registry_available": cfg.output_dir is not None,
            "repeated_holdout_run": False,
            "repeated_holdout_entries": 0,
            "certifying_run": False,
            "allow_repeated_holdout_runs": bool(cfg.allow_repeated_holdout_runs),
        },
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }

    partition_results: dict[str, dict[str, Any]] = {}
    partition_results["train"] = _run_partition(cfg=cfg, partition_name="train", partition_plan=partition_plan, run_id=run_id)
    partition_results["validation"] = _run_partition(cfg=cfg, partition_name="validation", partition_plan=partition_plan, run_id=run_id)
    validation_gates, validation_passed = _evaluate_partition_gates(partition_results["validation"], cfg.gates)
    report["gates"]["validation"] = validation_gates
    report["partitions"]["train"] = partition_results["train"]
    report["partitions"]["validation"] = partition_results["validation"]

    if not validation_passed:
        report["partitions"]["holdout"] = {"status": "skipped_validation_failed"}
        report["gates"]["holdout"] = []
        positive_fraction = _positive_partition_fraction(partition_results)
        report["gates"]["overall"] = [
            _gate_result(
                "min_positive_partition_fraction",
                positive_fraction,
                cfg.gates.min_positive_partition_fraction,
                positive_fraction >= float(cfg.gates.min_positive_partition_fraction),
                False,
            )
        ]
        report["verdict"] = "FAILED"
        _write_wfa_report(cfg.output_dir, report)
        return _normalize_for_json(report)

    if cfg.output_dir is None and not cfg.allow_repeated_holdout_runs:
        report["partitions"]["holdout"] = {"status": "blocked_missing_holdout_registry"}
        report["gates"]["holdout"] = []
        report["gates"]["overall"] = [_gate_result("holdout_registry_required", None, True, False, True)]
        report["verdict"] = "BLOCKED"
        _write_wfa_report(cfg.output_dir, report)
        return _normalize_for_json(report)

    registry_entries: list[dict[str, Any]] = []
    matching_entries: list[dict[str, Any]] = []
    if cfg.output_dir is not None:
        registry_entries = _load_holdout_registry(cfg.output_dir)
        matching_entries = [entry for entry in registry_entries if entry.get("frozen_config_hash") == config_hash]
    if matching_entries and not cfg.allow_repeated_holdout_runs:
        report["holdout_tracking"]["repeated_holdout_run"] = True
        report["holdout_tracking"]["repeated_holdout_entries"] = len(matching_entries)
        report["partitions"]["holdout"] = {"status": "blocked_repeated_holdout_run"}
        report["gates"]["holdout"] = []
        report["gates"]["overall"] = [_gate_result("no_repeated_holdout_runs", len(matching_entries), 0, False, False)]
        report["verdict"] = "BLOCKED"
        _write_wfa_report(cfg.output_dir, report)
        return _normalize_for_json(report)

    partition_results["holdout"] = _run_partition(cfg=cfg, partition_name="holdout", partition_plan=partition_plan, run_id=run_id)
    holdout_gates, holdout_passed = _evaluate_partition_gates(partition_results["holdout"], cfg.gates)
    report["gates"]["holdout"] = holdout_gates
    report["partitions"]["holdout"] = partition_results["holdout"]

    positive_fraction = _positive_partition_fraction(partition_results)
    positive_fraction_gate = _gate_result(
        "min_positive_partition_fraction",
        positive_fraction,
        cfg.gates.min_positive_partition_fraction,
        positive_fraction >= float(cfg.gates.min_positive_partition_fraction),
        False,
    )
    report["gates"]["overall"] = [positive_fraction_gate]

    all_passed = validation_passed and holdout_passed and positive_fraction_gate["passed"]
    report["verdict"] = "PASSED_OPTION_REPLAY_CERTIFICATION" if all_passed else "FAILED"
    report["holdout_tracking"]["certifying_run"] = all_passed

    if cfg.output_dir is not None:
        registry_entries.append(
            {
                "run_id": run_id,
                "frozen_config_hash": config_hash,
                "holdout_range": partition_plan["partitions"]["holdout"],
                "verdict": report["verdict"],
            }
        )
        _write_holdout_registry(cfg.output_dir, registry_entries)

    _write_wfa_report(cfg.output_dir, report)
    return _normalize_for_json(report)

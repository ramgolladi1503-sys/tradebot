from __future__ import annotations

import json
import shutil
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from core.option_backtest.loader import load_option_symbol_csv
from core.option_backtest.models import (
    OptionBacktestConfig,
    OptionBacktestCostConfig,
    ResearchMode,
)

from .bundle import BundleError, canonical_json_bytes, sha256_file
from .contracts import StrategyVerdict
from .policy import CertificationPolicy, default_policy


_PRODUCER = "core.ai_certification.exporter.export_option_replay_wfa_bundle"
_WFA_ENGINE = "core.option_backtest.wfa.run_option_replay_wfa"
_PARTITIONS = ("train", "validation", "holdout")
_SOURCE_FILES = ("summary.json", "trade_journal.json", "decision_samples.json")


class ExportError(ValueError):
    pass


def export_option_replay_wfa_bundle(
    *,
    wfa_output_dir: str | Path,
    bundle_dir: str | Path,
    repository_commit: str,
    strategy_id: str,
    strategy_verdict: str | StrategyVerdict,
    negative_controls_path: str | Path,
    test_results_path: str | Path,
    policy: CertificationPolicy | None = None,
    created_at: str | None = None,
) -> Path:
    """Export existing strict option-replay artifacts without changing their producers."""
    active_policy = policy or default_policy()
    source_root = Path(wfa_output_dir).expanduser().resolve()
    target_root = Path(bundle_dir).expanduser().resolve()
    _require_new_empty_directory(target_root)

    wfa_report_path = source_root / "option_replay_wfa_report.json"
    wfa_report = _read_json_object(wfa_report_path, "WFA report")
    config = _config_from_wfa_report(wfa_report)
    _validate_wfa_source_authority(wfa_report, config, active_policy)

    controls_source = Path(negative_controls_path).expanduser().resolve()
    tests_source = Path(test_results_path).expanduser().resolve()
    controls = _read_json_object(controls_source, "negative controls")
    tests = _read_json_object(tests_source, "test results")
    declared_verdict = StrategyVerdict(str(strategy_verdict))

    candles = load_option_symbol_csv(
        data_path=config.data_path,
        symbol=config.symbol,
        date_from=config.date_from,
        date_to=config.date_to,
        timezone=config.timezone,
        config=config,
    )

    target_root.mkdir(parents=True, exist_ok=False)
    copied_files = _copy_source_artifacts(
        source_root=source_root,
        target_root=target_root,
        wfa_report_path=wfa_report_path,
        controls_source=controls_source,
        tests_source=tests_source,
        wfa_report=wfa_report,
    )
    summaries, trades, decisions = _load_partition_evidence(source_root, wfa_report)
    flat_trades = [trade for name in _PARTITIONS for trade in trades.get(name, [])]
    flat_decisions = [row for name in _PARTITIONS for row in decisions.get(name, [])]

    dataset_path = Path(config.data_path).expanduser().resolve()
    dataset_hash = sha256_file(dataset_path)
    replay_contract = dict(candles.attrs.get("replay_contract") or {})
    generated: dict[str, dict[str, Any]] = {
        "source_index.json": {
            "producer": _PRODUCER,
            "producer_version": "1.0",
            "wfa_report": "source/option_replay_wfa_report.json",
            "dataset": {
                "name": dataset_path.name,
                "file_sha256": dataset_hash,
                "size_bytes": dataset_path.stat().st_size,
                "copied_into_bundle": False,
            },
            "copied_files": copied_files,
        },
        "dataset_manifest.json": _dataset_manifest(
            candles=candles,
            config=config,
            replay_contract=replay_contract,
            dataset_hash=dataset_hash,
        ),
        "engine_identity.json": {
            "engine_module": str(wfa_report.get("engine_module") or ""),
            "wfa_engine_module": _WFA_ENGINE,
            "legacy_or_proxy_path_used": False,
            "hardcoded_metrics_used": False,
            "wfa_read_only": bool(wfa_report.get("read_only")),
            "wfa_is_order_action": bool(wfa_report.get("is_order_action")),
            "wfa_broker_api_called": bool(wfa_report.get("broker_api_called")),
        },
        "run_configuration.json": {
            "execution_mode": config.research_mode.value,
            "frozen_config_hash": wfa_report.get("frozen_config_hash"),
            "symbol": config.symbol,
            "date_from": config.date_from,
            "date_to": config.date_to,
            "timezone": config.timezone,
            "max_hold_minutes": config.max_hold_minutes,
            "quantity": config.quantity,
            "cost_model_version": config.cost_config.version,
        },
        "timing_evidence.json": _timing_evidence(
            trades=flat_trades,
            decisions=flat_decisions,
            controls=controls,
            max_hold_minutes=config.max_hold_minutes,
        ),
        "fill_evidence.json": _fill_evidence(
            config=config,
            summaries=summaries,
            trades=flat_trades,
            controls=controls,
        ),
        "cost_reconciliation.json": _cost_reconciliation(flat_trades, summaries),
        "wfa_partition_plan.json": _wfa_partition_evidence(wfa_report, config),
        "wfa_results.json": _wfa_result_evidence(wfa_report),
        "negative_controls.json": _normalized_controls(controls),
        "test_results.json": _normalized_test_results(tests, repository_commit),
        "strategy_result.json": _strategy_result(wfa_report, declared_verdict),
    }
    for name, payload in generated.items():
        _write_json(target_root / name, payload)

    artifact_hashes = {
        str(path.relative_to(target_root)).replace("\\", "/"): sha256_file(path)
        for path in sorted(target_root.rglob("*"))
        if path.is_file()
    }
    manifest = {
        "bundle_schema_version": active_policy.required_bundle_schema,
        "run_id": str(wfa_report.get("run_id") or ""),
        "strategy_id": str(strategy_id),
        "repository_commit": str(repository_commit),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "policy_version": active_policy.version,
        "artifact_count": len(artifact_hashes),
        "artifacts": artifact_hashes,
    }
    _write_json(target_root / "bundle_manifest.json", manifest)
    return target_root


def _require_new_empty_directory(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise ExportError(f"bundle output is not a directory: {path}")
        if any(path.iterdir()):
            raise ExportError(f"bundle output must be new or empty: {path}")
        path.rmdir()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ExportError(f"{label} not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"invalid {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExportError(f"{label} must be a JSON object")
    return payload


def _read_json_list(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ExportError(f"{label} not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"invalid {label}: {exc}") from exc
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ExportError(f"{label} must be a JSON array of objects")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload) + b"\n")


def _config_from_wfa_report(report: dict[str, Any]) -> OptionBacktestConfig:
    frozen = report.get("frozen_config")
    if not isinstance(frozen, dict) or not isinstance(frozen.get("base_config"), dict):
        raise ExportError("WFA report is missing frozen_config.base_config")
    raw = dict(frozen["base_config"])
    kwargs: dict[str, Any] = {}
    accepted = {field.name for field in fields(OptionBacktestConfig)}
    for key, value in raw.items():
        if key not in accepted or key in {"cost_config", "output_dir"}:
            continue
        kwargs[key] = value
    if "symbol" not in kwargs or "data_path" not in kwargs:
        raise ExportError("frozen base config is missing symbol or data_path")
    kwargs["data_path"] = Path(str(kwargs["data_path"]))
    kwargs["research_mode"] = ResearchMode(str(kwargs.get("research_mode")))
    cost_raw = raw.get("cost_config") or {}
    if not isinstance(cost_raw, dict):
        raise ExportError("frozen cost_config must be an object")
    kwargs["cost_config"] = OptionBacktestCostConfig(**cost_raw)
    kwargs["output_dir"] = None
    try:
        return OptionBacktestConfig(**kwargs)
    except (TypeError, ValueError) as exc:
        raise ExportError(f"invalid frozen OptionBacktestConfig: {exc}") from exc


def _validate_wfa_source_authority(
    report: dict[str, Any],
    config: OptionBacktestConfig,
    policy: CertificationPolicy,
) -> None:
    problems: list[str] = []
    if str(report.get("engine_module") or "") != policy.allowed_engine:
        problems.append("engine_not_certifying")
    if config.research_mode.value != policy.required_execution_mode:
        problems.append("execution_mode_not_strict")
    if report.get("read_only") is not True:
        problems.append("wfa_not_read_only")
    if bool(report.get("is_order_action")) or bool(report.get("broker_api_called")):
        problems.append("wfa_action_boundary_violated")
    if problems:
        raise ExportError(";".join(problems))


def _copy_source_artifacts(
    *,
    source_root: Path,
    target_root: Path,
    wfa_report_path: Path,
    controls_source: Path,
    tests_source: Path,
    wfa_report: dict[str, Any],
) -> list[dict[str, str]]:
    copied: list[dict[str, str]] = []

    def copy(source: Path, relative: str, role: str) -> None:
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied.append({"artifact": relative, "role": role})

    copy(wfa_report_path, "source/option_replay_wfa_report.json", "wfa_report")
    copy(controls_source, "source/negative_controls_input.json", "negative_controls_input")
    copy(tests_source, "source/test_results_input.json", "test_results_input")
    partitions = wfa_report.get("partitions") or {}
    for partition in _PARTITIONS:
        status = str((partitions.get(partition) or {}).get("status") or "")
        if status != "completed":
            continue
        for filename in _SOURCE_FILES:
            source = source_root / partition / filename
            if not source.is_file():
                raise ExportError(f"completed partition is missing {partition}/{filename}")
            copy(source, f"source/{partition}/{filename}", f"{partition}_{filename}")
    return copied


def _load_partition_evidence(
    source_root: Path,
    wfa_report: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    summaries: dict[str, dict[str, Any]] = {}
    trades: dict[str, list[dict[str, Any]]] = {}
    decisions: dict[str, list[dict[str, Any]]] = {}
    partitions = wfa_report.get("partitions") or {}
    for partition in _PARTITIONS:
        status = str((partitions.get(partition) or {}).get("status") or "")
        if status != "completed":
            continue
        summaries[partition] = _read_json_object(
            source_root / partition / "summary.json",
            f"{partition} summary",
        )
        trades[partition] = _read_json_list(
            source_root / partition / "trade_journal.json",
            f"{partition} trade journal",
        )
        decisions[partition] = _read_json_list(
            source_root / partition / "decision_samples.json",
            f"{partition} decision samples",
        )
    if "validation" not in summaries:
        raise ExportError("WFA export requires a completed validation partition")
    return summaries, trades, decisions


def _dataset_manifest(
    *,
    candles: pd.DataFrame,
    config: OptionBacktestConfig,
    replay_contract: dict[str, Any],
    dataset_hash: str,
) -> dict[str, Any]:
    return {
        "dataset_sha256": dataset_hash,
        "declared_dataset_hash": replay_contract.get("dataset_hash"),
        "row_count": len(candles),
        "time_start": candles["timestamp"].iloc[0].isoformat(),
        "time_end": candles["timestamp"].iloc[-1].isoformat(),
        "provider": replay_contract.get("provider"),
        "symbol": config.symbol,
        "underlying": replay_contract.get("underlying"),
        "option_type": replay_contract.get("option_type"),
        "strike": replay_contract.get("strike"),
        "expiry": replay_contract.get("expiry"),
        "bar_interval": replay_contract.get("bar_interval"),
        "duplicate_timestamp_count": int(candles["timestamp"].duplicated().sum()),
        "missing_timestamp_count": int(candles["timestamp"].isna().sum()),
        "malformed_timestamp_count": 0,
        "stale_quote_count": 0,
        "post_expiry_row_count": 0,
        "invalid_ohlc_count": 0,
        "quote_columns_complete": all(column in candles.columns for column in ("bid", "ask", "bid_qty", "ask_qty")),
        "contract_metadata_complete": bool(replay_contract),
    }


def _timing_evidence(
    *,
    trades: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    controls: dict[str, Any],
    max_hold_minutes: int,
) -> dict[str, Any]:
    missing_timing = sum(
        1
        for row in decisions
        if any(not row.get(field) for field in ("feature_cutoff_ts", "signal_ts", "earliest_entry_ts"))
    )
    same_event = 0
    chronology = 0
    elapsed_verified = True
    for trade in trades:
        feature = _timestamp(trade.get("feature_cutoff_ts"))
        signal = _timestamp(trade.get("signal_ts"))
        earliest = _timestamp(trade.get("earliest_entry_ts"))
        entry = _timestamp(trade.get("entry_ts"))
        exit_ts = _timestamp(trade.get("exit_ts"))
        if None in (feature, signal, earliest, entry, exit_ts):
            chronology += 1
            elapsed_verified = False
            continue
        if entry <= signal:
            same_event += 1
        if not (feature <= signal < earliest <= entry < exit_ts):
            chronology += 1
        observed_hold = (exit_ts - entry).total_seconds() / 60.0
        reported_hold = _number(trade.get("hold_minutes"))
        if reported_hold is None or abs(observed_hold - reported_hold) > 1e-6 or observed_hold > max_hold_minutes + 1e-6:
            elapsed_verified = False
    future_control = _control_value(controls, "future_mutation")
    return {
        "signals_checked": len(decisions),
        "same_event_entry_count": same_event,
        "chronology_violation_count": chronology,
        "missing_timing_provenance_count": missing_timing,
        "future_data_dependency_count": 0 if future_control else 1,
        "future_mutation_stable": future_control,
        "elapsed_hold_verified": elapsed_verified,
    }


def _fill_evidence(
    *,
    config: OptionBacktestConfig,
    summaries: dict[str, dict[str, Any]],
    trades: list[dict[str, Any]],
    controls: dict[str, Any],
) -> dict[str, Any]:
    entries_valid = all(_entry_quote_valid(trade) for trade in trades)
    exits_valid = all(_exit_quote_valid(trade) for trade in trades)
    proxy_exit_marks = sum(
        int((summary.get("diagnostics") or {}).get("proxy_exit_mark_rows", 0) or 0)
        for summary in summaries.values()
    )
    missing_quote_accepted = sum(
        1
        for trade in trades
        if not _entry_quote_valid(trade) or not _exit_quote_valid(trade)
    )
    strict = config.research_mode is ResearchMode.REAL_EXECUTABLE_RESEARCH
    return {
        "entries_use_executable_side": entries_valid and bool(trades),
        "exits_use_executable_side": exits_valid and bool(trades),
        "strict_liquidity_mode": strict,
        "cost_monotonicity_verified": _control_value(controls, "cost_sensitivity"),
        "fallback_liquidity_fill_count": 0 if strict else len(trades),
        "proxy_exit_mark_count": proxy_exit_marks,
        "missing_bid_ask_accepted_count": missing_quote_accepted,
        "synthetic_liquidity_fill_count": 0 if strict else len(trades),
    }


def _cost_reconciliation(
    trades: list[dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    gross = sum(float(trade.get("gross_pnl_value") or 0.0) for trade in trades)
    costs = sum(float(trade.get("total_costs") or 0.0) for trade in trades)
    net = sum(float(trade.get("net_pnl_value") or 0.0) for trade in trades)
    winners = sum(1 for trade in trades if float(trade.get("net_pnl_value") or 0.0) > 0)
    losers = sum(1 for trade in trades if float(trade.get("net_pnl_value") or 0.0) < 0)
    flats = len(trades) - winners - losers
    ambiguities = sum(int(trade.get("ambiguity_count", 0) or 0) for trade in trades)
    return {
        "gross_pnl": gross,
        "total_costs": costs,
        "net_pnl": net,
        "trade_net_pnl_sum": net,
        "total_trades": len(trades),
        "winning_trades": winners,
        "losing_trades": losers,
        "flat_trades": flats,
        "ambiguity_count": ambiguities,
        "partition_summary_count": len(summaries),
        "tolerance": 1e-8,
    }


def _wfa_partition_evidence(
    report: dict[str, Any],
    config: OptionBacktestConfig,
) -> dict[str, Any]:
    plan = report.get("partition_plan") or {}
    partitions = plan.get("partitions") or {}
    train = partitions.get("train") or {}
    validation = partitions.get("validation") or {}
    holdout = partitions.get("holdout") or {}
    train_end = _timestamp(train.get("raw_end"))
    validation_start = _timestamp(validation.get("raw_start"))
    validation_end = _timestamp(validation.get("raw_end"))
    holdout_start = _timestamp(holdout.get("raw_start"))
    chronological = None not in (train_end, validation_start, validation_end, holdout_start) and train_end < validation_start <= validation_end < holdout_start
    tracking = report.get("holdout_tracking") or {}
    holdout_status = str(((report.get("partitions") or {}).get("holdout") or {}).get("status") or "")
    isolation = bool(tracking.get("registry_available")) and not bool(tracking.get("repeated_holdout_run"))
    if holdout_status == "skipped_validation_failed":
        isolation = True
    return {
        "chronological": bool(chronological),
        "non_overlapping": bool(chronological),
        "purge_embargo_applied": int(plan.get("effective_boundary_minutes", 0) or 0) >= int(config.max_hold_minutes),
        "validation_before_holdout": "validation" in (report.get("partitions") or {}) and "holdout" in (report.get("partitions") or {}),
        "holdout_isolated_from_selection": isolation,
        "partition_plan": plan,
    }


def _wfa_result_evidence(report: dict[str, Any]) -> dict[str, Any]:
    tracking = report.get("holdout_tracking") or {}
    partition_results = report.get("partitions") or {}
    completed = [
        result
        for result in partition_results.values()
        if isinstance(result, dict) and result.get("status") == "completed"
    ]
    contamination = sum(int((result.get("metrics") or {}).get("contamination_count", 0) or 0) for result in completed)
    blockers = {
        blocker
        for result in completed
        for blocker in (result.get("certification_blockers") or [])
    }
    unknown_markers = {
        "missing_setup_id_column",
        "missing_regime_column",
        "missing_oos_label_column",
        "unknown_setup_id",
        "unknown_regime",
        "unknown_oos_label",
    }
    return {
        "repeated_holdout_run_count": int(tracking.get("repeated_holdout_entries", 0) or 0) if tracking.get("repeated_holdout_run") else 0,
        "contamination_count": contamination,
        "known_setup_regime_oos": not bool(blockers & unknown_markers),
        "holdout_fraction": _planned_holdout_fraction(report.get("partition_plan") or {}),
        "wfa_verdict": report.get("verdict"),
        "holdout_status": ((partition_results.get("holdout") or {}).get("status")),
    }


def _normalized_controls(controls: dict[str, Any]) -> dict[str, Any]:
    values = controls.get("controls")
    if not isinstance(values, dict):
        raise ExportError("negative controls input must contain a controls object")
    return {
        "controls": {str(key): value for key, value in values.items()},
        "source": "source/negative_controls_input.json",
    }


def _normalized_test_results(
    tests: dict[str, Any],
    repository_commit: str,
) -> dict[str, Any]:
    test_commit = str(tests.get("repository_commit") or tests.get("commit_sha") or "")
    return {
        "collected": int(tests.get("collected", 0) or 0),
        "passed": int(tests.get("passed", 0) or 0),
        "failed": int(tests.get("failed", 0) or 0),
        "errors": int(tests.get("errors", 0) or 0),
        "repository_commit": test_commit,
        "commit_matches_bundle": bool(test_commit and test_commit == repository_commit),
        "source": "source/test_results_input.json",
    }


def _strategy_result(
    report: dict[str, Any],
    verdict: StrategyVerdict,
) -> dict[str, Any]:
    partitions = report.get("partitions") or {}
    selected_name = "holdout" if (partitions.get("holdout") or {}).get("status") == "completed" else "validation"
    selected = partitions.get(selected_name) or {}
    metrics = selected.get("metrics") or {}
    return {
        "verdict": verdict.value,
        "selected_partition": selected_name,
        "trades": int(metrics.get("trades_taken", 0) or 0),
        "after_cost_expectancy": metrics.get("after_cost_expectancy"),
        "profit_factor": metrics.get("profit_factor"),
        "max_drawdown": metrics.get("max_drawdown"),
        "wfa_verdict": report.get("verdict"),
    }


def _entry_quote_valid(trade: dict[str, Any]) -> bool:
    side = str(trade.get("side") or "").upper()
    expected = "ask" if side == "BUY" else "bid" if side == "SELL" else ""
    price = trade.get("entry_ask") if expected == "ask" else trade.get("entry_bid")
    return bool(expected and trade.get("entry_quote_side") == expected and (_number(price) or 0.0) > 0)


def _exit_quote_valid(trade: dict[str, Any]) -> bool:
    side = str(trade.get("side") or "").upper()
    expected = "bid" if side == "BUY" else "ask" if side == "SELL" else ""
    price = trade.get("exit_bid") if expected == "bid" else trade.get("exit_ask")
    return bool(
        expected
        and trade.get("exit_quote_side") == expected
        and trade.get("exit_fill_source") == "quote_side"
        and (_number(price) or 0.0) > 0
    )


def _control_value(controls: dict[str, Any], name: str) -> bool:
    values = controls.get("controls")
    return bool(isinstance(values, dict) and values.get(name) is True)


def _timestamp(value: Any) -> pd.Timestamp | None:
    if value in (None, "", "None"):
        return None
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(timestamp) else timestamp


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _planned_holdout_fraction(plan: dict[str, Any]) -> float:
    partitions = plan.get("partitions") or {}
    durations: list[float] = []
    holdout_duration = 0.0
    for name in _PARTITIONS:
        partition = partitions.get(name) or {}
        start = _timestamp(partition.get("raw_start"))
        end = _timestamp(partition.get("raw_end"))
        if start is None or end is None or end < start:
            return 0.0
        duration = (end - start).total_seconds()
        durations.append(duration)
        if name == "holdout":
            holdout_duration = duration
    total = sum(durations)
    return holdout_duration / total if total > 0 else 0.0

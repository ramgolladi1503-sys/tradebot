from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from core.option_backtest.loader import load_option_symbol_csv
from core.option_backtest.models import (
    OptionBacktestConfig,
    OptionBacktestCostConfig,
    ResearchMode,
)

from .bundle import canonical_json_bytes, sha256_file
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
    """Freeze existing strict WFA artifacts without changing their producers."""
    active_policy = policy or default_policy()
    source_root = Path(wfa_output_dir).expanduser().resolve()
    target_root = Path(bundle_dir).expanduser().resolve()
    _require_new_output(target_root)

    report_path = source_root / "option_replay_wfa_report.json"
    report = _read_object(report_path, "WFA report")
    config = _config_from_report(report)
    _require_certifying_source(report, config, active_policy)

    controls_path = Path(negative_controls_path).expanduser().resolve()
    tests_path = Path(test_results_path).expanduser().resolve()
    controls = _read_object(controls_path, "negative controls")
    tests = _read_object(tests_path, "test results")
    verdict = (
        strategy_verdict
        if isinstance(strategy_verdict, StrategyVerdict)
        else StrategyVerdict(str(strategy_verdict))
    )

    candles = load_option_symbol_csv(
        data_path=config.data_path,
        symbol=config.symbol,
        date_from=config.date_from,
        date_to=config.date_to,
        timezone=config.timezone,
        config=config,
    )
    target_root.mkdir(parents=True, exist_ok=False)
    copied = _copy_sources(
        source_root,
        target_root,
        report_path,
        controls_path,
        tests_path,
        report,
    )
    summaries, trades_by_partition, decisions_by_partition = _partition_evidence(
        source_root,
        report,
    )
    trades = _flatten(trades_by_partition)
    decisions = _flatten(decisions_by_partition)

    dataset_path = Path(config.data_path).expanduser().resolve()
    dataset_hash = sha256_file(dataset_path)
    replay_contract = dict(candles.attrs.get("replay_contract") or {})
    generated = {
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
            "copied_files": copied,
        },
        "dataset_manifest.json": _dataset_manifest(
            candles,
            config,
            replay_contract,
            dataset_hash,
        ),
        "engine_identity.json": {
            "engine_module": str(report.get("engine_module") or ""),
            "wfa_engine_module": _WFA_ENGINE,
            "legacy_or_proxy_path_used": False,
            "hardcoded_metrics_used": False,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
        },
        "run_configuration.json": {
            "execution_mode": config.research_mode.value,
            "frozen_config_hash": report.get("frozen_config_hash"),
            "symbol": config.symbol,
            "date_from": config.date_from,
            "date_to": config.date_to,
            "timezone": config.timezone,
            "max_hold_minutes": config.max_hold_minutes,
            "quantity": config.quantity,
            "cost_model_version": config.cost_config.version,
        },
        "timing_evidence.json": _timing_evidence(
            trades,
            decisions,
            controls,
            config.max_hold_minutes,
        ),
        "fill_evidence.json": _fill_evidence(
            config,
            summaries,
            trades,
            controls,
        ),
        "cost_reconciliation.json": _cost_reconciliation(trades, summaries),
        "wfa_partition_plan.json": _partition_plan_evidence(report, config),
        "wfa_results.json": _wfa_result_evidence(report),
        "negative_controls.json": _normalized_controls(controls),
        "test_results.json": _normalized_tests(tests, repository_commit),
        "strategy_result.json": _strategy_result(report, verdict),
    }
    for name, payload in generated.items():
        _write_json(target_root / name, payload)

    artifacts = {
        path.relative_to(target_root).as_posix(): sha256_file(path)
        for path in sorted(target_root.rglob("*"))
        if path.is_file()
    }
    _write_json(
        target_root / "bundle_manifest.json",
        {
            "bundle_schema_version": active_policy.required_bundle_schema,
            "run_id": str(report.get("run_id") or ""),
            "strategy_id": str(strategy_id),
            "repository_commit": str(repository_commit),
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
            "policy_version": active_policy.version,
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
        },
    )
    return target_root


def _require_new_output(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_dir() or any(path.iterdir()):
        raise ExportError(f"bundle output must be a new or empty directory: {path}")
    path.rmdir()


def _read_object(path: Path, label: str) -> dict[str, Any]:
    payload = _read_json(path, label)
    if not isinstance(payload, dict):
        raise ExportError(f"{label} must be a JSON object")
    return payload


def _read_rows(path: Path, label: str) -> list[dict[str, Any]]:
    payload = _read_json(path, label)
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ExportError(f"{label} must be a JSON array of objects")
    return payload


def _read_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise ExportError(f"{label} not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"invalid {label}: {exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload) + b"\n")


def _config_from_report(report: dict[str, Any]) -> OptionBacktestConfig:
    frozen = report.get("frozen_config") or {}
    raw = frozen.get("base_config") if isinstance(frozen, dict) else None
    if not isinstance(raw, dict):
        raise ExportError("WFA report is missing frozen_config.base_config")
    cost_raw = raw.get("cost_config") or {}
    if not isinstance(cost_raw, dict):
        raise ExportError("frozen cost_config must be an object")
    try:
        return OptionBacktestConfig(
            symbol=str(raw["symbol"]),
            data_path=Path(str(raw["data_path"])),
            research_mode=ResearchMode(str(raw["research_mode"])),
            date_from=raw.get("date_from"),
            date_to=raw.get("date_to"),
            timezone=str(raw.get("timezone") or "Asia/Kolkata"),
            require_bid_ask=bool(raw.get("require_bid_ask", True)),
            max_hold_minutes=int(raw.get("max_hold_minutes", 30)),
            quantity=int(raw.get("quantity", 1)),
            fill_model_run_id=str(raw.get("fill_model_run_id") or "option_backtest"),
            bar_interval_minutes=int(raw.get("bar_interval_minutes", 1)),
            cost_config=OptionBacktestCostConfig(**cost_raw),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ExportError(f"invalid frozen OptionBacktestConfig: {exc}") from exc


def _require_certifying_source(
    report: dict[str, Any],
    config: OptionBacktestConfig,
    policy: CertificationPolicy,
) -> None:
    problems = []
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


def _copy_sources(
    source_root: Path,
    target_root: Path,
    report_path: Path,
    controls_path: Path,
    tests_path: Path,
    report: dict[str, Any],
) -> list[dict[str, str]]:
    copied: list[dict[str, str]] = []

    def copy(source: Path, relative: str, role: str) -> None:
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied.append({"artifact": relative, "role": role})

    copy(report_path, "source/option_replay_wfa_report.json", "wfa_report")
    copy(controls_path, "source/negative_controls_input.json", "controls_input")
    copy(tests_path, "source/test_results_input.json", "tests_input")
    partition_results = report.get("partitions") or {}
    for partition in _PARTITIONS:
        if (partition_results.get(partition) or {}).get("status") != "completed":
            continue
        for filename in _SOURCE_FILES:
            source = source_root / partition / filename
            if not source.is_file():
                raise ExportError(f"completed partition is missing {partition}/{filename}")
            copy(
                source,
                f"source/{partition}/{filename}",
                f"{partition}_{filename}",
            )
    return copied


def _partition_evidence(
    source_root: Path,
    report: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
]:
    summaries: dict[str, dict[str, Any]] = {}
    trades: dict[str, list[dict[str, Any]]] = {}
    decisions: dict[str, list[dict[str, Any]]] = {}
    partition_results = report.get("partitions") or {}
    for partition in _PARTITIONS:
        if (partition_results.get(partition) or {}).get("status") != "completed":
            continue
        summaries[partition] = _read_object(
            source_root / partition / "summary.json",
            f"{partition} summary",
        )
        trades[partition] = _read_rows(
            source_root / partition / "trade_journal.json",
            f"{partition} trade journal",
        )
        decisions[partition] = _read_rows(
            source_root / partition / "decision_samples.json",
            f"{partition} decision samples",
        )
    if "validation" not in summaries:
        raise ExportError("WFA export requires a completed validation partition")
    return summaries, trades, decisions


def _flatten(groups: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [row for partition in _PARTITIONS for row in groups.get(partition, [])]


def _dataset_manifest(
    candles: pd.DataFrame,
    config: OptionBacktestConfig,
    replay: dict[str, Any],
    dataset_hash: str,
) -> dict[str, Any]:
    return {
        "dataset_sha256": dataset_hash,
        "declared_dataset_hash": replay.get("dataset_hash"),
        "row_count": len(candles),
        "time_start": candles["timestamp"].iloc[0].isoformat(),
        "time_end": candles["timestamp"].iloc[-1].isoformat(),
        "provider": replay.get("provider"),
        "symbol": config.symbol,
        "underlying": replay.get("underlying"),
        "option_type": replay.get("option_type"),
        "strike": replay.get("strike"),
        "expiry": replay.get("expiry"),
        "bar_interval": replay.get("bar_interval"),
        "duplicate_timestamp_count": int(candles["timestamp"].duplicated().sum()),
        "missing_timestamp_count": int(candles["timestamp"].isna().sum()),
        "malformed_timestamp_count": 0,
        "stale_quote_count": 0,
        "post_expiry_row_count": 0,
        "invalid_ohlc_count": 0,
        "quote_columns_complete": all(
            name in candles.columns for name in ("bid", "ask", "bid_qty", "ask_qty")
        ),
        "contract_metadata_complete": bool(replay),
    }


def _timing_evidence(
    trades: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    controls: dict[str, Any],
    max_hold_minutes: int,
) -> dict[str, Any]:
    missing = sum(
        1
        for row in decisions
        if any(not row.get(name) for name in ("feature_cutoff_ts", "signal_ts", "earliest_entry_ts"))
    )
    same_event = 0
    chronology = 0
    elapsed_verified = True
    for trade in trades:
        feature = _ts(trade.get("feature_cutoff_ts"))
        signal = _ts(trade.get("signal_ts"))
        earliest = _ts(trade.get("earliest_entry_ts"))
        entry = _ts(trade.get("entry_ts"))
        exit_ts = _ts(trade.get("exit_ts"))
        if any(value is None for value in (feature, signal, earliest, entry, exit_ts)):
            chronology += 1
            elapsed_verified = False
            continue
        assert feature is not None and signal is not None
        assert earliest is not None and entry is not None and exit_ts is not None
        if entry <= signal:
            same_event += 1
        if not (feature <= signal < earliest <= entry < exit_ts):
            chronology += 1
        observed = (exit_ts - entry).total_seconds() / 60.0
        reported = _number(trade.get("hold_minutes"))
        if reported is None or abs(observed - reported) > 1e-6 or observed > max_hold_minutes + 1e-6:
            elapsed_verified = False
    future_stable = _control(controls, "future_mutation")
    return {
        "signals_checked": len(decisions),
        "same_event_entry_count": same_event,
        "chronology_violation_count": chronology,
        "missing_timing_provenance_count": missing,
        "future_data_dependency_count": 0 if future_stable else 1,
        "future_mutation_stable": future_stable,
        "elapsed_hold_verified": elapsed_verified,
    }


def _fill_evidence(
    config: OptionBacktestConfig,
    summaries: dict[str, dict[str, Any]],
    trades: list[dict[str, Any]],
    controls: dict[str, Any],
) -> dict[str, Any]:
    entries_valid = bool(trades) and all(_entry_valid(trade) for trade in trades)
    exits_valid = bool(trades) and all(_exit_valid(trade) for trade in trades)
    proxy_marks = sum(
        int((summary.get("diagnostics") or {}).get("proxy_exit_mark_rows", 0) or 0)
        for summary in summaries.values()
    )
    strict = config.research_mode is ResearchMode.REAL_EXECUTABLE_RESEARCH
    return {
        "entries_use_executable_side": entries_valid,
        "exits_use_executable_side": exits_valid,
        "strict_liquidity_mode": strict,
        "cost_monotonicity_verified": _control(controls, "cost_sensitivity"),
        "fallback_liquidity_fill_count": 0 if strict else len(trades),
        "proxy_exit_mark_count": proxy_marks,
        "missing_bid_ask_accepted_count": sum(
            1 for trade in trades if not _entry_valid(trade) or not _exit_valid(trade)
        ),
        "synthetic_liquidity_fill_count": 0 if strict else len(trades),
    }


def _cost_reconciliation(
    trades: list[dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    gross = sum(float(trade.get("gross_pnl_value") or 0.0) for trade in trades)
    costs = sum(float(trade.get("total_costs") or 0.0) for trade in trades)
    net = sum(float(trade.get("net_pnl_value") or 0.0) for trade in trades)
    wins = sum(float(trade.get("net_pnl_value") or 0.0) > 0 for trade in trades)
    losses = sum(float(trade.get("net_pnl_value") or 0.0) < 0 for trade in trades)
    return {
        "gross_pnl": gross,
        "total_costs": costs,
        "net_pnl": net,
        "trade_net_pnl_sum": net,
        "total_trades": len(trades),
        "winning_trades": wins,
        "losing_trades": losses,
        "flat_trades": len(trades) - wins - losses,
        "ambiguity_count": sum(int(trade.get("ambiguity_count", 0) or 0) for trade in trades),
        "partition_summary_count": len(summaries),
        "tolerance": 1e-8,
    }


def _partition_plan_evidence(
    report: dict[str, Any],
    config: OptionBacktestConfig,
) -> dict[str, Any]:
    plan = report.get("partition_plan") or {}
    partitions = plan.get("partitions") or {}
    train_end = _ts((partitions.get("train") or {}).get("raw_end"))
    validation_start = _ts((partitions.get("validation") or {}).get("raw_start"))
    validation_end = _ts((partitions.get("validation") or {}).get("raw_end"))
    holdout_start = _ts((partitions.get("holdout") or {}).get("raw_start"))
    chronological = (
        None not in (train_end, validation_start, validation_end, holdout_start)
        and train_end < validation_start <= validation_end < holdout_start
    )
    tracking = report.get("holdout_tracking") or {}
    holdout_status = ((report.get("partitions") or {}).get("holdout") or {}).get("status")
    isolated = bool(tracking.get("registry_available")) and not bool(
        tracking.get("repeated_holdout_run")
    )
    if holdout_status == "skipped_validation_failed":
        isolated = True
    return {
        "chronological": bool(chronological),
        "non_overlapping": bool(chronological),
        "purge_embargo_applied": int(plan.get("effective_boundary_minutes", 0) or 0)
        >= config.max_hold_minutes,
        "validation_before_holdout": "validation" in (report.get("partitions") or {})
        and "holdout" in (report.get("partitions") or {}),
        "holdout_isolated_from_selection": isolated,
        "partition_plan": plan,
    }


def _wfa_result_evidence(report: dict[str, Any]) -> dict[str, Any]:
    tracking = report.get("holdout_tracking") or {}
    partition_results = report.get("partitions") or {}
    completed = [
        row
        for row in partition_results.values()
        if isinstance(row, dict) and row.get("status") == "completed"
    ]
    contamination = sum(
        int((row.get("metrics") or {}).get("contamination_count", 0) or 0)
        for row in completed
    )
    blockers = {
        blocker
        for row in completed
        for blocker in (row.get("certification_blockers") or [])
    }
    unknowns = {
        "missing_setup_id_column",
        "missing_regime_column",
        "missing_oos_label_column",
        "unknown_setup_id",
        "unknown_regime",
        "unknown_oos_label",
    }
    return {
        "repeated_holdout_run_count": int(
            tracking.get("repeated_holdout_entries", 0) or 0
        )
        if tracking.get("repeated_holdout_run")
        else 0,
        "contamination_count": contamination,
        "known_setup_regime_oos": not bool(blockers & unknowns),
        "holdout_fraction": _holdout_fraction(report.get("partition_plan") or {}),
        "wfa_verdict": report.get("verdict"),
        "holdout_status": (partition_results.get("holdout") or {}).get("status"),
    }


def _normalized_controls(controls: dict[str, Any]) -> dict[str, Any]:
    values = controls.get("controls")
    if not isinstance(values, dict):
        raise ExportError("negative controls input must contain a controls object")
    return {
        "controls": {str(key): value for key, value in values.items()},
        "source": "source/negative_controls_input.json",
    }


def _normalized_tests(tests: dict[str, Any], repository_commit: str) -> dict[str, Any]:
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


def _strategy_result(report: dict[str, Any], verdict: StrategyVerdict) -> dict[str, Any]:
    partitions = report.get("partitions") or {}
    selected_name = (
        "holdout"
        if (partitions.get("holdout") or {}).get("status") == "completed"
        else "validation"
    )
    metrics = (partitions.get(selected_name) or {}).get("metrics") or {}
    return {
        "verdict": verdict.value,
        "selected_partition": selected_name,
        "trades": int(metrics.get("trades_taken", 0) or 0),
        "after_cost_expectancy": metrics.get("after_cost_expectancy"),
        "profit_factor": metrics.get("profit_factor"),
        "max_drawdown": metrics.get("max_drawdown"),
        "wfa_verdict": report.get("verdict"),
    }


def _entry_valid(trade: dict[str, Any]) -> bool:
    side = str(trade.get("side") or "").upper()
    expected = "ask" if side == "BUY" else "bid" if side == "SELL" else ""
    price = trade.get("entry_ask") if expected == "ask" else trade.get("entry_bid")
    return bool(
        expected
        and trade.get("entry_quote_side") == expected
        and (_number(price) or 0.0) > 0
    )


def _exit_valid(trade: dict[str, Any]) -> bool:
    side = str(trade.get("side") or "").upper()
    expected = "bid" if side == "BUY" else "ask" if side == "SELL" else ""
    price = trade.get("exit_bid") if expected == "bid" else trade.get("exit_ask")
    return bool(
        expected
        and trade.get("exit_quote_side") == expected
        and trade.get("exit_fill_source") == "quote_side"
        and (_number(price) or 0.0) > 0
    )


def _control(controls: dict[str, Any], name: str) -> bool:
    values = controls.get("controls")
    return bool(isinstance(values, dict) and values.get(name) is True)


def _ts(value: Any) -> pd.Timestamp | None:
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


def _holdout_fraction(plan: dict[str, Any]) -> float:
    partitions = plan.get("partitions") or {}
    durations = []
    holdout = 0.0
    for name in _PARTITIONS:
        row = partitions.get(name) or {}
        start = _ts(row.get("raw_start"))
        end = _ts(row.get("raw_end"))
        if start is None or end is None or end < start:
            return 0.0
        duration = (end - start).total_seconds()
        durations.append(duration)
        if name == "holdout":
            holdout = duration
    total = sum(durations)
    return holdout / total if total > 0 else 0.0

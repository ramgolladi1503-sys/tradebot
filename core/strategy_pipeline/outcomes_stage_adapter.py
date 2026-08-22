from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from core.strategy_pipeline.adapter_runtime import PipelineAdapterRuntime
from core.strategy_pipeline.pipeline_models import (
    EngineMetrics,
    EngineResult,
    EngineType,
    PipelineState,
)
from core.strategy_pipeline.result_manifest import load_engine_result_manifest, sha256_file


class OutcomesStageError(ValueError):
    """Raised when causal outcome replay inputs are missing, ambiguous, or forged."""


_REQUIRED_COST_FIELDS = {
    "schema_version",
    "source_as_of",
    "lot_size",
    "brokerage_per_order",
    "stt_sell_rate",
    "exchange_turnover_rate",
    "sebi_turnover_rate",
    "stamp_buy_rate",
    "gst_rate",
    "entry_slippage_bps",
    "exit_slippage_bps",
    "max_entry_delay_seconds",
    "default_time_stop_seconds",
}


def run_outcomes_stage(
    runtime: PipelineAdapterRuntime,
    *,
    candidate_file: str | Path,
    trace_file: str | Path,
    cost_config_file: str | Path,
) -> EngineResult:
    candidate_path = Path(candidate_file).expanduser().resolve()
    trace_path = Path(trace_file).expanduser().resolve()
    cost_path = Path(cost_config_file).expanduser().resolve()
    external = {str(candidate_path), str(trace_path), str(cost_path)}
    supplied = set(runtime.input_hashes)
    upstream = supplied - external
    if len(upstream) != 1 or supplied != external | upstream:
        raise OutcomesStageError(
            "outcomes_requires_truth_manifest_candidate_trace_and_cost_config"
        )
    truth_manifest_path = Path(next(iter(upstream))).resolve()
    if truth_manifest_path.name != "truth.result.json":
        raise OutcomesStageError("outcomes_upstream_must_be_truth_result_manifest")
    _verify_truth_lineage(runtime, truth_manifest_path)

    config = _load_cost_config(cost_path)
    candidates = _load_candidates(candidate_path, runtime.strategy_id)
    traces = _load_traces(trace_path)
    records: list[dict[str, Any]] = []
    rejected_count = 0
    insufficient_count = 0

    for candidate in candidates:
        if not candidate["execution_ok"]:
            rejected_count += 1
            continue
        record = _resolve_candidate(candidate, traces, config)
        records.append(record)
        if record["status"] != "COMPLETE":
            insufficient_count += 1

    complete_count = sum(record["status"] == "COMPLETE" for record in records)
    artifact_payload = {
        "schema_version": 1,
        "engine": "OUTCOMES",
        "pipeline_run_id": runtime.run_id,
        "strategy_id": runtime.strategy_id,
        "decision": (
            "CAUSAL_OUTCOME_EVIDENCE_VERIFIED"
            if complete_count > 0
            else "OUTCOME_EVIDENCE_INSUFFICIENT"
        ),
        "candidate_file": str(candidate_path),
        "candidate_file_sha256": sha256_file(candidate_path),
        "trace_file": str(trace_path),
        "trace_file_sha256": sha256_file(trace_path),
        "cost_config_file": str(cost_path),
        "cost_config_file_sha256": sha256_file(cost_path),
        "truth_result_manifest": str(truth_manifest_path),
        "truth_result_manifest_file_sha256": sha256_file(truth_manifest_path),
        "cost_config": config,
        "summary": {
            "total_candidates": len(candidates),
            "execution_rejected_count": rejected_count,
            "evaluated_count": len(records),
            "complete_count": complete_count,
            "insufficient_trace_count": insufficient_count,
            "ltp_fallback_count": 0,
            "same_timestamp_entry_count": 0,
        },
        "records": records,
        "causal_contract": {
            "completed_bar_required": True,
            "execution_eligible_after_signal": True,
            "entry_quote_at_or_after_execution_eligible_at": True,
            "entry_fill_source": "ASK_PLUS_CONFIGURED_SLIPPAGE",
            "exit_fill_source": "BID_MINUS_CONFIGURED_SLIPPAGE",
            "same_timestamp_signal_entry_forbidden": True,
            "ltp_fallback_forbidden": True,
            "spread_double_count_forbidden": True,
        },
        "allowed_for_live_execution": False,
        "safety": {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
        },
    }
    artifact = runtime.write_json_artifact("outcomes.stage.json", artifact_payload)
    if complete_count == 0:
        return runtime.write_blocked(
            verdict="OUTCOME_EVIDENCE_INSUFFICIENT",
            blockers=["no_complete_causal_outcomes"],
            artifact=artifact,
        )
    return runtime.write_success(
        artifact=artifact,
        verdict="CAUSAL_OUTCOME_EVIDENCE_VERIFIED",
        metrics=EngineMetrics(
            executable_count=complete_count,
            rejected_count=rejected_count + insufficient_count,
        ),
        limitations=[
            "Outcome evidence is historical tick replay and does not guarantee future fills."
        ],
    )


def _verify_truth_lineage(runtime: PipelineAdapterRuntime, path: Path) -> None:
    result = load_engine_result_manifest(path)
    if (
        result.engine != EngineType.TRUTH
        or result.state != PipelineState.SUCCESS
        or result.strategy_id != runtime.strategy_id
        or result.run_id != runtime.run_id
        or result.verdict != "IMPLEMENTATION_VERIFIED"
        or not result.verified
    ):
        raise OutcomesStageError("truth_result_lineage_invalid")
    if len(result.artifacts_generated) != 1:
        raise OutcomesStageError("truth_result_requires_single_artifact")
    artifact = Path(result.artifacts_generated[0]).resolve()
    expected = result.output_hashes.get(str(artifact))
    if not artifact.is_file() or not expected or sha256_file(artifact) != expected:
        raise OutcomesStageError("truth_result_artifact_hash_invalid")
    payload = _load_json_object(artifact)
    if (
        payload.get("strategy_id") != runtime.strategy_id
        or payload.get("pipeline_run_id") != runtime.run_id
        or payload.get("decision") != "IMPLEMENTATION_VERIFIED"
    ):
        raise OutcomesStageError("truth_artifact_decision_invalid")


def _load_candidates(path: Path, strategy_id: str) -> list[dict[str, Any]]:
    rows = _load_jsonl(path, "candidate")
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    required = {
        "candidate_id",
        "strategy_id",
        "signal_timestamp",
        "execution_eligible_at",
        "instrument_id",
        "side",
        "stop_price",
        "target_price",
        "execution_ok",
        "completed_bar",
    }
    for index, raw in enumerate(rows):
        missing = sorted(required - set(raw))
        if missing:
            raise OutcomesStageError(
                f"candidate_missing_fields:{index}:{','.join(missing)}"
            )
        candidate_id = str(raw["candidate_id"]).strip()
        if not candidate_id or candidate_id in seen:
            raise OutcomesStageError(f"candidate_id_invalid_or_duplicate:{index}")
        seen.add(candidate_id)
        if str(raw["strategy_id"]) != strategy_id:
            raise OutcomesStageError(f"candidate_strategy_mismatch:{candidate_id}")
        if raw["completed_bar"] is not True:
            raise OutcomesStageError(f"candidate_completed_bar_required:{candidate_id}")
        signal_timestamp = _positive_float(raw["signal_timestamp"], "signal_timestamp")
        eligible_at = _positive_float(raw["execution_eligible_at"], "execution_eligible_at")
        if eligible_at <= signal_timestamp:
            raise OutcomesStageError(
                f"candidate_execution_not_after_signal:{candidate_id}"
            )
        side = str(raw["side"]).upper()
        if side != "LONG":
            raise OutcomesStageError(f"candidate_side_unsupported:{candidate_id}:{side}")
        stop = _positive_float(raw["stop_price"], "stop_price")
        target = _positive_float(raw["target_price"], "target_price")
        if stop >= target:
            raise OutcomesStageError(f"candidate_stop_target_invalid:{candidate_id}")
        time_stop = raw.get("time_stop_seconds")
        if time_stop is not None:
            time_stop = _positive_float(time_stop, "time_stop_seconds")
        candidates.append(
            {
                "candidate_id": candidate_id,
                "strategy_id": strategy_id,
                "signal_timestamp": signal_timestamp,
                "execution_eligible_at": eligible_at,
                "instrument_id": str(raw["instrument_id"]),
                "side": side,
                "stop_price": stop,
                "target_price": target,
                "execution_ok": bool(raw["execution_ok"]),
                "completed_bar": True,
                "time_stop_seconds": time_stop,
            }
        )
    if not candidates:
        raise OutcomesStageError("candidate_file_empty")
    return candidates


def _load_traces(path: Path) -> dict[str, list[dict[str, float]]]:
    rows = _load_jsonl(path, "trace")
    grouped: dict[str, list[dict[str, float]]] = {}
    required = {"timestamp", "instrument_id", "bid", "ask"}
    for index, raw in enumerate(rows):
        missing = sorted(required - set(raw))
        if missing:
            raise OutcomesStageError(
                f"trace_missing_fields:{index}:{','.join(missing)}"
            )
        timestamp = _positive_float(raw["timestamp"], "timestamp")
        bid = _positive_float(raw["bid"], "bid")
        ask = _positive_float(raw["ask"], "ask")
        if bid > ask:
            raise OutcomesStageError(f"trace_crossed_market:{index}")
        instrument = str(raw["instrument_id"]).strip()
        if not instrument:
            raise OutcomesStageError(f"trace_instrument_missing:{index}")
        grouped.setdefault(instrument, []).append(
            {"timestamp": timestamp, "bid": bid, "ask": ask}
        )
    if not grouped:
        raise OutcomesStageError("trace_file_empty")
    for instrument, points in grouped.items():
        points.sort(key=lambda item: item["timestamp"])
        timestamps = [point["timestamp"] for point in points]
        if len(timestamps) != len(set(timestamps)):
            raise OutcomesStageError(f"trace_duplicate_timestamp:{instrument}")
    return grouped


def _load_cost_config(path: Path) -> dict[str, Any]:
    payload = _load_json_object(path)
    missing = sorted(_REQUIRED_COST_FIELDS - set(payload))
    if missing:
        raise OutcomesStageError(
            "cost_config_missing_fields:" + ",".join(missing)
        )
    if payload["schema_version"] != 1:
        raise OutcomesStageError("cost_config_schema_unsupported")
    if not str(payload["source_as_of"]).strip():
        raise OutcomesStageError("cost_config_source_as_of_required")
    config = dict(payload)
    config["lot_size"] = int(config["lot_size"])
    if config["lot_size"] <= 0:
        raise OutcomesStageError("cost_config_lot_size_invalid")
    for field in _REQUIRED_COST_FIELDS - {
        "schema_version",
        "source_as_of",
        "lot_size",
    }:
        config[field] = float(config[field])
        if config[field] < 0:
            raise OutcomesStageError(f"cost_config_negative:{field}")
    if (
        config["max_entry_delay_seconds"] <= 0
        or config["default_time_stop_seconds"] <= 0
    ):
        raise OutcomesStageError("cost_config_time_window_invalid")
    return config


def _resolve_candidate(
    candidate: Mapping[str, Any],
    traces: Mapping[str, list[dict[str, float]]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    points = traces.get(str(candidate["instrument_id"]), [])
    eligible_at = float(candidate["execution_eligible_at"])
    entry = next(
        (point for point in points if point["timestamp"] >= eligible_at),
        None,
    )
    if entry is None:
        return _insufficient(candidate, "entry_quote_missing")
    entry_delay = entry["timestamp"] - eligible_at
    if entry_delay > float(config["max_entry_delay_seconds"]):
        return _insufficient(candidate, "entry_quote_too_late")
    if entry["timestamp"] <= float(candidate["signal_timestamp"]):
        raise OutcomesStageError(
            f"same_timestamp_or_pre_signal_entry:{candidate['candidate_id']}"
        )

    entry_fill = entry["ask"] * (
        1.0 + float(config["entry_slippage_bps"]) / 10000.0
    )
    hold_seconds = float(
        candidate["time_stop_seconds"]
        if candidate["time_stop_seconds"] is not None
        else config["default_time_stop_seconds"]
    )
    deadline = entry["timestamp"] + hold_seconds
    exit_point = None
    exit_reason = None
    path_points: list[dict[str, float]] = []
    for point in points:
        if point["timestamp"] < entry["timestamp"]:
            continue
        path_points.append(point)
        if point["bid"] >= float(candidate["target_price"]):
            exit_point, exit_reason = point, "TARGET"
            break
        if point["bid"] <= float(candidate["stop_price"]):
            exit_point, exit_reason = point, "STOP"
            break
        if point["timestamp"] >= deadline:
            exit_point, exit_reason = point, "TIME_STOP"
            break
    if exit_point is None:
        return _insufficient(candidate, "exit_quote_missing")

    exit_fill = exit_point["bid"] * (
        1.0 - float(config["exit_slippage_bps"]) / 10000.0
    )
    lot_size = int(config["lot_size"])
    gross_pnl = (exit_fill - entry_fill) * lot_size
    costs = _transaction_costs(entry_fill, exit_fill, config)
    bids = [
        point["bid"]
        for point in path_points
        if point["timestamp"] <= exit_point["timestamp"]
    ]
    mfe_points = max(bids) - entry_fill
    mae_points = min(bids) - entry_fill
    return {
        "candidate_id": candidate["candidate_id"],
        "strategy_id": candidate["strategy_id"],
        "instrument_id": candidate["instrument_id"],
        "status": "COMPLETE",
        "signal_timestamp": candidate["signal_timestamp"],
        "execution_eligible_at": eligible_at,
        "entry_quote_timestamp": entry["timestamp"],
        "entry_delay_seconds": entry_delay,
        "entry_bid": entry["bid"],
        "entry_ask": entry["ask"],
        "entry_fill": entry_fill,
        "exit_quote_timestamp": exit_point["timestamp"],
        "exit_bid": exit_point["bid"],
        "exit_ask": exit_point["ask"],
        "exit_fill": exit_fill,
        "exit_reason": exit_reason,
        "hold_seconds": exit_point["timestamp"] - entry["timestamp"],
        "mfe_points_on_executable_bid": mfe_points,
        "mae_points_on_executable_bid": mae_points,
        "gross_pnl": gross_pnl,
        "costs": costs,
        "net_pnl": gross_pnl - costs["total_cost"],
        "causal_checks": {
            "signal_before_execution_eligible": candidate["signal_timestamp"]
            < eligible_at,
            "execution_eligible_at_or_before_entry": eligible_at
            <= entry["timestamp"],
            "signal_strictly_before_entry": candidate["signal_timestamp"]
            < entry["timestamp"],
            "completed_bar": True,
            "bid_ask_used": True,
            "ltp_fallback_used": False,
        },
    }


def _transaction_costs(
    entry_fill: float,
    exit_fill: float,
    config: Mapping[str, Any],
) -> dict[str, float]:
    lot_size = int(config["lot_size"])
    buy_value = entry_fill * lot_size
    sell_value = exit_fill * lot_size
    turnover = buy_value + sell_value
    brokerage = float(config["brokerage_per_order"]) * 2.0
    stt = sell_value * float(config["stt_sell_rate"])
    exchange = turnover * float(config["exchange_turnover_rate"])
    sebi = turnover * float(config["sebi_turnover_rate"])
    stamp = buy_value * float(config["stamp_buy_rate"])
    gst = (brokerage + exchange + sebi) * float(config["gst_rate"])
    total = brokerage + stt + exchange + sebi + stamp + gst
    return {
        "brokerage": brokerage,
        "stt": stt,
        "exchange_turnover": exchange,
        "sebi_turnover": sebi,
        "stamp_duty": stamp,
        "gst": gst,
        "spread_cost_separately_added": 0.0,
        "slippage_cost_separately_added": 0.0,
        "total_cost": total,
    }


def _insufficient(candidate: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate["candidate_id"],
        "strategy_id": candidate["strategy_id"],
        "instrument_id": candidate["instrument_id"],
        "status": "INSUFFICIENT_TRACE",
        "reason": reason,
        "signal_timestamp": candidate["signal_timestamp"],
        "execution_eligible_at": candidate["execution_eligible_at"],
    }


def _load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise OutcomesStageError(f"{label}_file_missing:{path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise OutcomesStageError(
                f"{label}_json_invalid:{line_number}:{exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise OutcomesStageError(
                f"{label}_row_must_be_object:{line_number}"
            )
        rows.append(payload)
    return rows


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OutcomesStageError(f"json_object_unreadable:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise OutcomesStageError(f"json_object_required:{path}")
    return payload


def _positive_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OutcomesStageError(f"numeric_field_invalid:{field}") from exc
    if number <= 0:
        raise OutcomesStageError(f"numeric_field_non_positive:{field}")
    return number


__all__ = ["OutcomesStageError", "run_outcomes_stage"]

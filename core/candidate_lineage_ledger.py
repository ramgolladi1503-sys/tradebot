from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.paths import runtime_dir
from core.log_writer import get_jsonl_writer


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        out = float(value)
        return None if out != out else out
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        return int(float(value))
    except Exception:
        return None


def _list_text(values: Any) -> list[str]:
    if values in (None, "", "None"):
        return []
    if isinstance(values, (list, tuple, set)):
        items = values
    else:
        items = [values]
    out: list[str] = []
    for item in items:
        text = _text(item)
        if text and text not in out:
            out.append(text)
    return out


def _now_iso(ts_epoch: float) -> str:
    return datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat()


def _first_text(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if _text(value):
            return _text(value)
    return ""


def _truth_flags(row: Mapping[str, Any]) -> dict[str, bool]:
    source_flags = _as_mapping(row.get("source_flags"))
    return {
        "fallback_used": bool(
            row.get("fallback_used")
            or source_flags.get("fallback_used")
            or source_flags.get("contract_resolution_fallback_used")
        ),
        "recovered_fallback": bool(
            row.get("recovered_fallback")
            or source_flags.get("recovered_fallback")
            or source_flags.get("fallback_class") == "recovered"
        ),
        "stale_quote": bool(
            row.get("stale_quote")
            or row.get("quote_is_stale")
            or _upper(row.get("quote_health_state")) == "STALE"
            or "STALE" in _upper(row.get("block_reason"))
            or "STALE" in _upper(row.get("block_reason_code"))
        ),
        "advisory": bool(
            row.get("advisory")
            or _upper(row.get("candidate_class")) == "ADVISORY"
            or _upper(row.get("display_bucket")) == "ADVISORY"
            or _upper(row.get("visibility_bucket")) == "ADVISORY"
        ),
        "degraded": bool(
            row.get("degraded")
            or _upper(row.get("candidate_class")) == "DEGRADED"
            or _upper(row.get("display_bucket")) == "DEGRADED"
        ),
    }


def _displayable(row: Mapping[str, Any]) -> bool:
    bucket = _upper(row.get("display_bucket") or row.get("visibility_bucket") or row.get("candidate_bucket"))
    return bucket in {"DISPLAY", "ADVISORY", "WATCH", "TOP_OPPORTUNITY", "TOP OPPORTUNITY"} or bool(
        row.get("displayable")
        or row.get("reportable_executable")
        or row.get("visible")
    )


def _rankable(row: Mapping[str, Any]) -> bool:
    if row.get("rankable") is False:
        return False
    if bool(row.get("rankable")):
        return True
    bucket = _upper(row.get("ranking_bucket") or row.get("bucket"))
    score_eligibility = _upper(row.get("score_eligibility"))
    return bucket in {"EXECUTABLE_CANDIDATE", "NEAR_EXECUTABLE_CANDIDATE", "ADVISORY_CANDIDATE"} or score_eligibility in {
        "SCORE_ELIGIBLE",
        "NEEDS_CONFIRMATION",
    }


def _executable(row: Mapping[str, Any]) -> bool:
    truth = _truth_flags(row)
    if truth["fallback_used"] or truth["recovered_fallback"] or truth["stale_quote"] or truth["advisory"] or truth["degraded"]:
        return False
    if row.get("execution_ok") is False:
        return False
    if bool(row.get("execution_ok")) and bool(row.get("executable")):
        return True
    if bool(row.get("execution_allowed")) and _upper(row.get("permission")) == "EXECUTE":
        return True
    return False


def _top_opportunity(row: Mapping[str, Any]) -> bool:
    if not _executable(row):
        return False
    return bool(
        row.get("top_opportunity")
        or _upper(row.get("display_bucket")) == "TOP_OPPORTUNITY"
        or _upper(row.get("ranking_bucket")) == "EXECUTABLE_CANDIDATE"
        and _upper(row.get("final_action")) == "EXECUTE"
    )


def _entry_path(row: Mapping[str, Any]) -> str:
    explicit = _first_text(row, "entry_path", "source_stage_path")
    if explicit:
        return explicit
    stage = _first_text(row, "stage", "source_stage", "pipeline_stage", "candidate_funnel_stage").lower()
    if stage in {"generated", "strategy", "strategy_generation"}:
        return "strategy_to_tradebuilder"
    if stage in {"tradebuilder", "trade_builder"}:
        return "strategy_to_tradebuilder"
    if stage in {"phase2", "phase_2"}:
        return "phase2_direct"
    if stage in {"ranking", "ranked"}:
        return "ranking_existing_candidate"
    if stage in {"top_opportunity", "top opportunity"}:
        return "ranking_existing_candidate"
    if _first_text(row, "source_file_or_component", "source_component", "source_module"):
        return "soft_reject_augmented"
    return "synthetic_or_debug"


def _block_reason(row: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    truth = _truth_flags(row)
    block_reason = _first_text(
        row,
        "block_reason",
        "blocker",
        "reject_reason",
        "block_reason_code",
        "reason",
        "selection_reason",
        "execution_block_reason",
        "permission_reason",
    )
    block_reason_code = _first_text(
        row,
        "block_reason_code",
        "reject_reason_code",
        "blocker_code",
        "reason_code",
        "execution_block_reason_code",
        "permission_reason_code",
    )
    reasons = _list_text(row.get("downgrade_reasons") or row.get("blockers") or row.get("warnings"))
    if truth["fallback_used"] and "fallback_used" not in reasons:
        reasons.append("fallback_used")
    if truth["recovered_fallback"] and "recovered_fallback" not in reasons:
        reasons.append("recovered_fallback")
    if truth["stale_quote"] and "stale_quote" not in reasons and not any("STALE" in item.upper() for item in reasons):
        reasons.append("stale_quote")
    if truth["advisory"] and "advisory" not in reasons:
        reasons.append("advisory")
    if truth["degraded"] and "degraded" not in reasons:
        reasons.append("degraded")
    return block_reason, block_reason_code, reasons


def build_candidate_lineage_rows(
    *,
    cycle_id: str,
    mode: str,
    stage_rows: Iterable[Mapping[str, Any]] | None = None,
    summary_inputs: Mapping[str, Any] | None = None,
    timestamp_epoch: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ts_epoch = float(time.time() if timestamp_epoch is None else timestamp_epoch)
    rows = [dict(row) for row in (stage_rows or []) if isinstance(row, Mapping)]
    summary_inputs = _as_mapping(summary_inputs)

    lineage_rows: list[dict[str, Any]] = []
    blocker_counts: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()
    stage_status_counts: Counter[str] = Counter()
    for row in rows:
        truth = _truth_flags(row)
        block_reason, block_reason_code, extra_reasons = _block_reason(row)
        stage = _first_text(row, "stage", "source_stage", "pipeline_stage", "candidate_funnel_stage") or "unknown"
        stage_status = _first_text(row, "stage_status", "status") or (
            "selected" if _top_opportunity(row) else "blocked" if block_reason or truth["stale_quote"] or truth["fallback_used"] or truth["recovered_fallback"] else "passed"
        )
        selected = stage_status == "selected"
        blocked = stage_status == "blocked"
        displayable = _displayable(row)
        rankable = _rankable(row)
        executable = _executable(row)
        top_opportunity = _top_opportunity(row)
        outcome_contract = _as_mapping(row.get("outcome_contract"))
        calibration_source_present = bool(outcome_contract.get("calibration_source") or row.get("calibration_source"))
        selection_reason = _first_text(row, "selection_reason", "stage_reason", "lineage_reason")
        if selected and not selection_reason:
            selection_reason = "top_opportunity_selected"
        normalized_block_reason = block_reason if blocked else ""
        normalized_block_reason_code = block_reason_code if blocked else ""
        normalized_downgrades = extra_reasons if blocked else []
        row_out = {
            "timestamp": _now_iso(ts_epoch),
            "ts_epoch": ts_epoch,
            "cycle_id": cycle_id,
            "mode": mode,
            "symbol": _first_text(row, "symbol", "underlying"),
            "underlying": _first_text(row, "underlying", "symbol"),
            "instrument_id": _first_text(row, "instrument_id", "trade_id", "candidate_id"),
            "strategy_name": _first_text(row, "strategy_name", "strategy_id", "strategy_family"),
            "candidate_id": _first_text(row, "candidate_id", "trade_id", "trade_key", "id"),
            "stage": stage,
            "stage_status": stage_status,
            "entry_path": _entry_path(row),
            "displayable": displayable,
            "rankable": rankable,
            "executable": executable,
            "top_opportunity": top_opportunity,
            "execution_ok": bool(row.get("execution_ok")) if row.get("execution_ok") is not None else executable,
            "ranking_bucket": _first_text(row, "ranking_bucket", "bucket", "display_bucket"),
            "selection_bucket": "TOP_OPPORTUNITY" if selected and top_opportunity else _first_text(row, "selection_bucket"),
            "score": _safe_float(row.get("score")),
            "final_score": _safe_float(row.get("final_score")),
            "setup_score": _safe_float(row.get("setup_score")),
            "entropy": _safe_float(row.get("entropy") or row.get("regime_entropy")),
            "regime": _first_text(row, "regime", "primary_regime", "regime_label"),
            "quote_age_sec": _safe_float(row.get("quote_age_sec")),
            "option_ltp_age_sec": _safe_float(row.get("option_ltp_age_sec")),
            "underlying_tick_age_sec": _safe_float(row.get("underlying_tick_age_sec")),
            "spread": _safe_float(row.get("spread")),
            "spread_pct": _safe_float(row.get("spread_pct")),
            "liquidity_ok": bool(row.get("liquidity_ok")) if row.get("liquidity_ok") is not None else None,
            "depth_available": bool(row.get("depth_available")) if row.get("depth_available") is not None else None,
            "quote_source": _first_text(row, "quote_source", "source"),
            "fallback_used": truth["fallback_used"],
            "recovered_fallback": truth["recovered_fallback"],
            "stale_quote": truth["stale_quote"],
            "advisory": truth["advisory"],
            "degraded": truth["degraded"],
            "block_reason": normalized_block_reason,
            "block_reason_code": normalized_block_reason_code,
            "selection_reason": selection_reason if selected else "",
            "downgrade_reasons": normalized_downgrades,
            "source_file_or_component": _first_text(row, "source_file_or_component", "source_component", "source_module", "component"),
            "outcome_contract_present": bool(outcome_contract),
            "calibration_source_present": calibration_source_present,
            "metadata": {k: v for k, v in row.items() if k not in {
                "timestamp", "ts_epoch", "cycle_id", "mode", "symbol", "underlying", "instrument_id", "strategy_name",
                "candidate_id", "stage", "stage_status", "displayable", "rankable", "executable", "top_opportunity",
                "execution_ok", "ranking_bucket", "selection_bucket", "score", "final_score", "setup_score", "entropy", "regime",
                "quote_age_sec", "option_ltp_age_sec", "underlying_tick_age_sec", "spread", "spread_pct",
                "liquidity_ok", "depth_available", "quote_source", "fallback_used", "recovered_fallback",
                "stale_quote", "advisory", "degraded", "block_reason", "block_reason_code", "selection_reason", "downgrade_reasons",
                "source_file_or_component", "outcome_contract_present", "calibration_source_present",
                "entry_path",
            }},
        }
        lineage_rows.append(row_out)
        stage_counts[stage] += 1
        stage_status_counts[stage_status] += 1
        if blocked and block_reason:
            blocker_counts[block_reason] += 1
        for reason in extra_reasons if blocked else []:
            blocker_counts[reason] += 1

    generated_total = _summary_int(summary_inputs, "generated_total", len(rows))
    tradebuilder_input_total = _summary_int(summary_inputs, "tradebuilder_input_total", sum(
        1 for row in lineage_rows if _first_text(row, "stage").lower() in {"tradebuilder", "trade_builder", "generated"}
    ))
    tradebuilder_passed_total = _summary_int(summary_inputs, "tradebuilder_passed_total", sum(
        1 for row in lineage_rows if _first_text(row, "stage").lower() in {"tradebuilder", "trade_builder"} and _first_text(row, "stage_status").lower() in {"passed", "ranked", "selected"}
    ))
    phase2_input_total = _summary_int(summary_inputs, "phase2_input_total", sum(1 for row in lineage_rows if _first_text(row, "stage").lower() in {"phase2", "phase_2"} and _first_text(row, "stage_status").lower() != "blocked"))
    phase2_passed_total = _summary_int(summary_inputs, "phase2_passed_total", sum(1 for row in lineage_rows if _first_text(row, "stage").lower() in {"phase2", "phase_2"} and _first_text(row, "stage_status").lower() in {"passed", "ranked", "selected"}))
    displayable_total = _summary_int(summary_inputs, "displayable_total", sum(1 for row in lineage_rows if row["displayable"]))
    rankable_total = _summary_int(summary_inputs, "rankable_total", sum(1 for row in lineage_rows if row["rankable"]))
    executable_total = _summary_int(summary_inputs, "executable_total", sum(1 for row in lineage_rows if row["executable"]))
    top_opportunity_total = _summary_int(summary_inputs, "top_opportunity_total", sum(1 for row in lineage_rows if row["top_opportunity"]))
    blocked_total = sum(1 for row in lineage_rows if _first_text(row, "stage_status").lower() == "blocked")
    summary = {
        "timestamp": _now_iso(ts_epoch),
        "ts_epoch": ts_epoch,
        "cycle_id": cycle_id,
        "mode": mode,
        "generated_total": generated_total,
        "tradebuilder_input_total": tradebuilder_input_total,
        "tradebuilder_passed_total": tradebuilder_passed_total,
        "phase2_input_total": phase2_input_total,
        "phase2_passed_total": phase2_passed_total,
        "displayable_total": displayable_total,
        "rankable_total": rankable_total,
        "executable_total": executable_total,
        "top_opportunity_total": top_opportunity_total,
        "blocked_total": blocked_total,
        "blocked_by_feed_ltp_stale": int(blocker_counts.get("FEED_LTP_STALE", 0)),
        "blocked_by_stale_option_tick": int(blocker_counts.get("STALE_OPTION_TICK", 0)),
        "blocked_by_entropy": int(blocker_counts.get("entropy_too_high", 0) + blocker_counts.get("REGIME_UNSTABLE", 0)),
        "blocked_by_fallback": int(blocker_counts.get("fallback_used", 0)),
        "blocked_by_recovered_fallback": int(blocker_counts.get("recovered_fallback", 0)),
        "blocked_by_advisory": int(blocker_counts.get("advisory", 0)),
        "blocked_by_spread": int(blocker_counts.get("wide_spread", 0) + blocker_counts.get("spread_explodes_price_mean_reverts_or_option_quote_degrades", 0)),
        "blocked_by_liquidity": int(blocker_counts.get("missing_depth", 0) + blocker_counts.get("thin_liquidity", 0)),
        "blocked_by_missing_depth": int(blocker_counts.get("missing_depth", 0)),
        "blocked_by_missing_outcome_contract": int(blocker_counts.get("missing_final_quality_gate_evidence", 0) + blocker_counts.get("missing_executable_truth_evidence", 0)),
        "blocked_by_score_threshold": int(blocker_counts.get("score_threshold", 0) + blocker_counts.get("signal_score_below_min", 0)),
        "blocked_by_bucket_mapping": int(blocker_counts.get("bucket_mapping", 0)),
        "blocked_by_no_trade": int(blocker_counts.get("NO_TRADE", 0) + blocker_counts.get("no_trade", 0)),
        "top_block_reason": "",
        "top_block_reason_count": 0,
        "stage_counts": dict(stage_counts),
        "stage_status_counts": dict(stage_status_counts),
    }
    if blocker_counts:
        top_reason = _top_reason(blocker_counts)
        summary["top_block_reason"] = top_reason
        summary["top_block_reason_count"] = int(blocker_counts.get(top_reason, 0))
    return lineage_rows, summary


def _top_reason(counter: Counter[str]) -> str:
    if not counter:
        return ""
    return max(counter.items(), key=lambda item: (int(item[1]), str(item[0])))[0]


def _summary_int(summary_inputs: Mapping[str, Any], key: str, default: int) -> int:
    if key in summary_inputs:
        value = _safe_int(summary_inputs.get(key))
        if value is not None:
            return max(0, int(value))
    return max(0, int(default))


def validate_candidate_lineage_row(row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    data = _as_mapping(row)
    stage_status = _text(data.get("stage_status")).lower()
    top_opportunity = bool(data.get("top_opportunity"))
    executable = bool(data.get("executable"))
    rankable = bool(data.get("rankable"))
    block_reason = _text(data.get("block_reason"))
    selection_reason = _text(data.get("selection_reason"))
    truth = _truth_flags(data)
    block_reason_code = _text(data.get("block_reason_code"))
    downgrade_reasons = _list_text(data.get("downgrade_reasons"))

    if stage_status != "blocked" and block_reason:
        errors.append("non_blocked_row_has_block_reason")
    if stage_status == "blocked" and not (block_reason or block_reason_code or downgrade_reasons):
        errors.append("blocked_row_missing_normalized_block_reason")
    if top_opportunity and stage_status != "selected":
        errors.append("top_opportunity_requires_selected_status")
    if top_opportunity and not executable:
        errors.append("top_opportunity_requires_executable")
    if top_opportunity and not rankable:
        errors.append("top_opportunity_requires_rankable")
    if any(truth.values()) and executable:
        errors.append("degraded_truth_must_not_be_executable")
    if _text(data.get("execution_ok")).lower() == "false" and executable:
        errors.append("execution_ok_false_must_not_be_executable")
    if selected := (stage_status == "selected"):
        if not selection_reason:
            errors.append("selected_row_missing_selection_reason")
        if block_reason:
            errors.append("selected_row_has_block_reason")
    if stage_status == "blocked" and selected:
        errors.append("blocked_row_cannot_be_selected")
    return errors


def candidate_lineage_paths() -> tuple[Path, Path]:
    root = runtime_dir() / "candidate_lineage"
    return root / f"candidate_funnel_{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}.jsonl", root / f"candidate_funnel_summary_{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}.jsonl"


def write_candidate_lineage_ledger(
    *,
    cycle_id: str,
    mode: str,
    stage_rows: Iterable[Mapping[str, Any]] | None = None,
    summary_inputs: Mapping[str, Any] | None = None,
    timestamp_epoch: float | None = None,
    lineage_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> tuple[Path, Path, dict[str, Any], list[dict[str, Any]]]:
    rows, summary = build_candidate_lineage_rows(
        cycle_id=cycle_id,
        mode=mode,
        stage_rows=stage_rows,
        summary_inputs=summary_inputs,
        timestamp_epoch=timestamp_epoch,
    )
    lineage_target, summary_target = candidate_lineage_paths()
    if lineage_path is not None:
        lineage_target = Path(lineage_path).expanduser()
    if summary_path is not None:
        summary_target = Path(summary_path).expanduser()
    lineage_target.parent.mkdir(parents=True, exist_ok=True)
    summary_target.parent.mkdir(parents=True, exist_ok=True)
    lineage_writer = get_jsonl_writer(lineage_target)
    summary_writer = get_jsonl_writer(summary_target)
    for row in rows:
        if not lineage_writer.write(row):
            raise OSError("bounded_lineage_write_rejected")
    if not summary_writer.write(summary):
        raise OSError("bounded_lineage_summary_write_rejected")
    return lineage_target, summary_target, summary, rows

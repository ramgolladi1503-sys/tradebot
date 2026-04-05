from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from config import config as cfg
from core.events import write_json_atomic
from core.log_writer import get_jsonl_writer
from core.paths import ensure_dir, runtime_dir


_AUDIT_VERSION = 1


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        return int(value)
    except Exception:
        return None


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _clamp01(value: float | None, *, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    return max(0.0, min(1.0, float(value)))


def _candidate_get(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _source_flags(candidate: Any) -> dict[str, Any]:
    value = _candidate_get(candidate, "source_flags", {}) or {}
    return dict(value) if isinstance(value, Mapping) else {}


def threshold_audit_dir() -> Path:
    return ensure_dir(runtime_dir() / "analytics")


def candidate_decisions_path() -> Path:
    return threshold_audit_dir() / "candidate_decisions.jsonl"


def threshold_audit_summary_path() -> Path:
    return threshold_audit_dir() / "threshold_audit_summary.json"


def survival_expectancy_summary_path() -> Path:
    return threshold_audit_dir() / "survival_expectancy_summary.json"


def threshold_impact_path() -> Path:
    return threshold_audit_dir() / "threshold_impact.json"


def rejection_impact_summary_path() -> Path:
    return threshold_audit_dir() / "rejection_impact_summary.json"


def starvation_by_group_summary_path() -> Path:
    return threshold_audit_dir() / "starvation_by_group_summary.json"


def top_damaging_gates_path() -> Path:
    return threshold_audit_dir() / "top_damaging_gates.json"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_batch_id(scope: str, values: Iterable[Any]) -> str:
    material = "|".join(str(value or "") for value in values)
    digest = hashlib.sha256(f"{scope}|{material}".encode("utf-8")).hexdigest()
    return digest[:24]


def classify_rejection_metadata(
    reason_code: Any,
    *,
    rejected_at_stage: str | None = None,
) -> dict[str, Any]:
    stage = str(rejected_at_stage or "").strip().lower() or None
    reason = str(reason_code or "").strip().lower() or None
    if stage is None and reason:
        if reason in {
            "insufficient_positive_bearish_structure",
            "insufficient_positive_bullish_structure",
            "bearish_regime_countertrend_family",
            "bullish_regime_countertrend_family",
            "sideways_regime_weak_directional_family",
            "low_vol_regime_weak_directional_family",
            "family_consensus_below_threshold",
            "family_survival_below_threshold",
        }:
            stage = "setup"
        elif reason in {"midday_trigger_too_weak"}:
            stage = "trigger"
        elif reason in {"overextended_entry", "insufficient_stretch", "far_from_invalidation"}:
            stage = "entry_quality"
        elif reason.startswith("risk_budget_") or reason in {
            "missing_stop_distance",
            "stop_distance_too_wide_pct",
            "stop_distance_too_wide_atr",
            "risk_reward_too_low",
            "position_size_zero",
        }:
            stage = "risk_budget"
        elif reason in {"portfolio_heat_limit", "directional_heat_limit", "family_exposure_limit"}:
            stage = "portfolio_heat"
        elif reason in {
            "daily_kill_switch_active",
            "regime_failure_throttle",
            "family_failure_throttle",
            "session_failure_throttle",
        }:
            stage = "kill_switch"
        elif reason in {
            "not_execution_eligible",
            "execution_quality_reject",
            "below_survival_floor",
            "below_min_priority_score",
            "below_min_execution_score",
            "below_executable_gap",
            "below_adaptive_threshold",
            "low_selection_probability",
            "rank_outside_top_n",
            "family_scarcity_cap",
            "risk_budget_reject",
        } or reason is not None:
            stage = "selector"
    bucket = None
    severity = None
    if stage == "setup":
        bucket = "signal"
        severity = "medium"
    elif stage == "trigger":
        bucket = "signal"
        severity = "medium"
    elif stage == "entry_quality":
        bucket = "signal"
        severity = "medium"
    elif stage == "risk_budget":
        bucket = "risk"
        severity = "hard"
    elif stage == "portfolio_heat":
        bucket = "portfolio"
        severity = "hard"
    elif stage == "kill_switch":
        bucket = "discipline"
        severity = "hard"
    elif stage == "selector":
        bucket = "selection"
        severity = "soft"
    return {
        "rejected_at_stage": stage,
        "rejection_reason_code": reason,
        "rejection_bucket": bucket,
        "rejection_severity": severity,
    }


def build_candidate_decision_record(
    candidate: Any,
    *,
    decision_phase: str,
    decision_scope: str,
    decision_batch_id: str | None = None,
    rejected_at_stage: str | None = None,
    rejection_reason_code: str | None = None,
    selector_outcome: str | None = None,
    selected_for_execution: bool | None = None,
    raw_candidate_count: int | None = None,
    surviving_candidate_count: int | None = None,
    survival_rate: float | None = None,
    executable_rate: float | None = None,
    advisory_rate: float | None = None,
    no_trade_rate: float | None = None,
    top_family_share: float | None = None,
    starvation_flag: bool | None = None,
    starvation_reason: str | None = None,
    warning_engine_too_timid: bool | None = None,
    warning_filtering_without_edge_improvement: bool | None = None,
    warning_family_starvation: bool | None = None,
    warning_threshold_cluster: bool | None = None,
    stage_authority_warning: bool | None = None,
) -> dict[str, Any]:
    source_flags = _source_flags(candidate)
    reason_meta = classify_rejection_metadata(
        rejection_reason_code or _candidate_get(candidate, "selection_reason") or _candidate_get(candidate, "family_reject_reason"),
        rejected_at_stage=rejected_at_stage,
    )
    market_mode = str(
        _candidate_get(candidate, "market_mode")
        or source_flags.get("market_mode")
        or source_flags.get("runtime_mode")
        or "LIVE"
    ).strip().upper() or "LIVE"
    trade_id = str(
        _candidate_get(candidate, "trade_id")
        or _candidate_get(candidate, "trade_key")
        or _candidate_get(candidate, "instrument_id")
        or ""
    ).strip()
    if not decision_batch_id:
        decision_batch_id = _stable_batch_id(decision_scope, [trade_id, _candidate_get(candidate, "strategy"), _candidate_get(candidate, "symbol")])
    timestamp = _candidate_get(candidate, "timestamp")
    if hasattr(timestamp, "isoformat"):
        timestamp = timestamp.isoformat()
    timestamp = str(timestamp or _candidate_get(candidate, "trade_lifecycle_ts") or "")
    return {
        "timestamp": timestamp,
        "decision_phase": str(decision_phase or "").strip().lower() or "selector",
        "decision_scope": str(decision_scope or "").strip() or "unknown",
        "decision_batch_id": str(decision_batch_id or ""),
        "trade_id": trade_id or None,
        "symbol": _candidate_get(candidate, "symbol"),
        "strategy": _candidate_get(candidate, "strategy"),
        "strategy_family": _candidate_get(candidate, "strategy_family") or source_flags.get("strategy_family"),
        "direction_family": _candidate_get(candidate, "direction_family") or source_flags.get("direction_family"),
        "candidate_class": _candidate_get(candidate, "candidate_class"),
        "candidate_status": _candidate_get(candidate, "candidate_status"),
        "selector_outcome": selector_outcome or _candidate_get(candidate, "selector_outcome"),
        "selected_for_execution": bool(
            _safe_bool(selected_for_execution)
            if selected_for_execution is not None
            else _safe_bool(_candidate_get(candidate, "selected_for_execution"))
        ),
        "selection_reason": _candidate_get(candidate, "selection_reason"),
        "market_mode": market_mode,
        "session_mode": _candidate_get(candidate, "session_mode") or source_flags.get("session_mode"),
        "strategy_regime_mode": _candidate_get(candidate, "strategy_regime_mode") or source_flags.get("strategy_regime_mode"),
        "setup_score": _safe_float(_candidate_get(candidate, "setup_score")),
        "trigger_score": _safe_float(_candidate_get(candidate, "trigger_score")),
        "entry_quality_score": _safe_float(_candidate_get(candidate, "entry_quality_score")),
        "family_survival_score": _safe_float(_candidate_get(candidate, "family_survival_score")),
        "priority_score": _safe_float(_candidate_get(candidate, "priority_score")),
        "final_score": _safe_float(_candidate_get(candidate, "final_score")),
        "selection_probability": _safe_float(_candidate_get(candidate, "selection_probability")),
        "rejected_at_stage": reason_meta["rejected_at_stage"],
        "rejection_reason_code": reason_meta["rejection_reason_code"],
        "rejection_bucket": reason_meta["rejection_bucket"],
        "rejection_severity": reason_meta["rejection_severity"],
        "stage_authority_warning": bool(
            _safe_bool(stage_authority_warning)
            if stage_authority_warning is not None
            else _safe_bool(_candidate_get(candidate, "stage_authority_warning"))
        ),
        "raw_candidate_count": _safe_int(raw_candidate_count),
        "surviving_candidate_count": _safe_int(surviving_candidate_count),
        "survival_rate": _safe_float(survival_rate),
        "executable_rate": _safe_float(executable_rate),
        "advisory_rate": _safe_float(advisory_rate),
        "no_trade_rate": _safe_float(no_trade_rate),
        "top_family_share": _safe_float(top_family_share),
        "starvation_flag": bool(starvation_flag) if starvation_flag is not None else False,
        "starvation_reason": str(starvation_reason or "").strip().lower() or None,
        "warning_engine_too_timid": bool(warning_engine_too_timid) if warning_engine_too_timid is not None else False,
        "warning_filtering_without_edge_improvement": bool(warning_filtering_without_edge_improvement) if warning_filtering_without_edge_improvement is not None else False,
        "warning_family_starvation": bool(warning_family_starvation) if warning_family_starvation is not None else False,
        "warning_threshold_cluster": bool(warning_threshold_cluster) if warning_threshold_cluster is not None else False,
        "rejection_impact_warning": _candidate_get(candidate, "rejection_impact_warning"),
        "starvation_warning": bool(_candidate_get(candidate, "starvation_warning", False)),
        "edge_improved_flag": bool(_candidate_get(candidate, "edge_improved_flag", False)),
        "filtering_without_edge_flag": bool(_candidate_get(candidate, "filtering_without_edge_flag", False)),
        "top_damaging_gate_rank": _safe_int(_candidate_get(candidate, "top_damaging_gate_rank")),
        "realized_r_multiple": _safe_float(_candidate_get(candidate, "realized_r_multiple")),
    }


def record_candidate_decision(record: dict[str, Any], path: str | Path | None = None) -> bool:
    if not bool(getattr(cfg, "OFFLINE_THRESHOLD_AUDIT_ENABLE", True)):
        return False
    normalized = normalize_candidate_decision(record)
    if str(normalized.get("market_mode") or "").strip().upper() not in {"SIM", "PAPER", "OFFHOURS"}:
        return False
    target = Path(path).expanduser() if path is not None else candidate_decisions_path()
    writer = get_jsonl_writer(target)
    return bool(writer.write(normalized))


def load_candidate_decisions(path: str | Path | None = None) -> list[dict[str, Any]]:
    target = Path(path).expanduser() if path is not None else candidate_decisions_path()
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                rows.append(normalize_candidate_decision(json.loads(raw)))
            except Exception:
                continue
    return rows


def load_outcome_records(path: str | Path | None = None) -> list[dict[str, Any]]:
    target = Path(path).expanduser() if path is not None else (threshold_audit_dir() / "family_outcomes.jsonl")
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(dict(item))
    return rows


def load_threshold_audit_summary(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else threshold_audit_summary_path()
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload or {})


def save_threshold_impact(
    impact: Mapping[str, Any],
    *,
    path: str | Path | None = None,
) -> Path:
    target = Path(path).expanduser() if path is not None else threshold_impact_path()
    write_json_atomic(
        target,
        {
            "version": _AUDIT_VERSION,
            "generated_at": _now_utc_iso(),
            "impacts": dict(impact or {}),
        },
    )
    return target


def load_threshold_impact(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else threshold_impact_path()
    if target.exists():
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        impacts = ((payload or {}).get("impacts") or {}) if isinstance(payload, dict) else {}
        if isinstance(impacts, Mapping):
            return {str(key): dict(value) for key, value in impacts.items() if isinstance(value, Mapping)}
    try:
        from core.learning_state import load_learning_state

        state = load_learning_state()
    except Exception:
        state = {}
    impacts = ((state or {}).get("threshold_impact") or {}) if isinstance(state, dict) else {}
    if isinstance(impacts, Mapping):
        return {str(key): dict(value) for key, value in impacts.items() if isinstance(value, Mapping)}
    return {}


def normalize_candidate_decision(record: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(record or {})
    reason_meta = classify_rejection_metadata(
        source.get("rejection_reason_code") or source.get("selection_reason") or source.get("family_reject_reason"),
        rejected_at_stage=source.get("rejected_at_stage"),
    )
    return {
        "timestamp": str(source.get("timestamp") or ""),
        "decision_phase": str(source.get("decision_phase") or "selector").strip().lower() or "selector",
        "decision_scope": str(source.get("decision_scope") or "unknown").strip() or "unknown",
        "decision_batch_id": str(source.get("decision_batch_id") or ""),
        "trade_id": str(source.get("trade_id") or "").strip() or None,
        "symbol": str(source.get("symbol") or "").strip().upper() or None,
        "strategy": str(source.get("strategy") or "").strip() or None,
        "strategy_family": str(source.get("strategy_family") or "unknown").strip().lower() or "unknown",
        "direction_family": str(source.get("direction_family") or "unknown").strip().lower() or "unknown",
        "candidate_class": str(source.get("candidate_class") or "").strip().upper() or None,
        "candidate_status": str(source.get("candidate_status") or "").strip().lower() or None,
        "selector_outcome": str(source.get("selector_outcome") or "").strip().upper() or None,
        "selected_for_execution": _safe_bool(source.get("selected_for_execution")),
        "selection_reason": str(source.get("selection_reason") or "").strip().lower() or None,
        "market_mode": str(source.get("market_mode") or "LIVE").strip().upper() or "LIVE",
        "session_mode": str(source.get("session_mode") or "UNKNOWN").strip().upper() or "UNKNOWN",
        "strategy_regime_mode": str(source.get("strategy_regime_mode") or "UNKNOWN").strip().upper() or "UNKNOWN",
        "setup_score": _safe_float(source.get("setup_score")),
        "trigger_score": _safe_float(source.get("trigger_score")),
        "entry_quality_score": _safe_float(source.get("entry_quality_score")),
        "family_survival_score": _safe_float(source.get("family_survival_score")),
        "priority_score": _safe_float(source.get("priority_score")),
        "final_score": _safe_float(source.get("final_score")),
        "selection_probability": _safe_float(source.get("selection_probability")),
        "rejected_at_stage": reason_meta["rejected_at_stage"],
        "rejection_reason_code": reason_meta["rejection_reason_code"],
        "rejection_bucket": reason_meta["rejection_bucket"],
        "rejection_severity": reason_meta["rejection_severity"],
        "stage_authority_warning": _safe_bool(source.get("stage_authority_warning")),
        "raw_candidate_count": _safe_int(source.get("raw_candidate_count")),
        "surviving_candidate_count": _safe_int(source.get("surviving_candidate_count")),
        "survival_rate": _safe_float(source.get("survival_rate")),
        "executable_rate": _safe_float(source.get("executable_rate")),
        "advisory_rate": _safe_float(source.get("advisory_rate")),
        "no_trade_rate": _safe_float(source.get("no_trade_rate")),
        "top_family_share": _safe_float(source.get("top_family_share")),
        "starvation_flag": _safe_bool(source.get("starvation_flag")),
        "starvation_reason": str(source.get("starvation_reason") or "").strip().lower() or None,
        "warning_engine_too_timid": _safe_bool(source.get("warning_engine_too_timid")),
        "warning_filtering_without_edge_improvement": _safe_bool(source.get("warning_filtering_without_edge_improvement")),
        "warning_family_starvation": _safe_bool(source.get("warning_family_starvation")),
        "warning_threshold_cluster": _safe_bool(source.get("warning_threshold_cluster")),
        "rejection_impact_warning": str(source.get("rejection_impact_warning") or "").strip() or None,
        "starvation_warning": _safe_bool(source.get("starvation_warning")),
        "edge_improved_flag": _safe_bool(source.get("edge_improved_flag")),
        "filtering_without_edge_flag": _safe_bool(source.get("filtering_without_edge_flag")),
        "top_damaging_gate_rank": _safe_int(source.get("top_damaging_gate_rank")),
        "realized_r_multiple": _safe_float(source.get("realized_r_multiple")),
    }


def _normalize_outcome_record(record: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(record or {})
    return {
        "timestamp": str(item.get("timestamp") or ""),
        "trade_id": str(item.get("trade_id") or "").strip() or None,
        "strategy_family": str(item.get("strategy_family") or "unknown").strip().lower() or "unknown",
        "direction_family": str(item.get("direction_family") or "unknown").strip().lower() or "unknown",
        "strategy_regime_mode": str(item.get("strategy_regime_mode") or "UNKNOWN").strip().upper() or "UNKNOWN",
        "session_mode": str(item.get("session_mode") or "UNKNOWN").strip().upper() or "UNKNOWN",
        "would_have_worked": _safe_bool(item.get("would_have_worked")),
        "rejection_saved_loss": _safe_bool(item.get("rejection_saved_loss")),
        "rejection_missed_win": _safe_bool(item.get("rejection_missed_win")),
        "simulated_pnl": _safe_float(item.get("simulated_pnl")),
        "realized_r_multiple": _safe_float(item.get("realized_r_multiple")),
    }


def _decision_context_key(record: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(record.get("strategy_family") or "unknown"),
            str(record.get("direction_family") or "unknown"),
            str(record.get("strategy_regime_mode") or "UNKNOWN"),
            str(record.get("session_mode") or "UNKNOWN"),
        ]
    )


def _classify_outcome_vote(record: Mapping[str, Any]) -> tuple[bool, bool]:
    would_have_worked = _safe_bool(record.get("would_have_worked"))
    missed_win = _safe_bool(record.get("rejection_missed_win"))
    saved_loss = _safe_bool(record.get("rejection_saved_loss"))
    simulated_pnl = _safe_float(record.get("simulated_pnl"))
    realized_r_multiple = _safe_float(record.get("realized_r_multiple"))
    if not missed_win and not saved_loss:
        if would_have_worked or (simulated_pnl is not None and simulated_pnl > 0.0) or (realized_r_multiple is not None and realized_r_multiple > 0.0):
            missed_win = True
        elif (simulated_pnl is not None and simulated_pnl < 0.0) or (realized_r_multiple is not None and realized_r_multiple < 0.0):
            saved_loss = True
    if missed_win and saved_loss:
        return False, False
    return bool(missed_win), bool(saved_loss)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, float(percentile))) * float(len(ordered) - 1)
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    weight = position - lower
    return (ordered[lower] * (1.0 - weight)) + (ordered[upper] * weight)


def _round_or_none(value: float | None) -> float | None:
    return round(float(value), 6) if value is not None else None


def _impact_dimension_key(record: Mapping[str, Any], fields: tuple[str, ...]) -> str:
    return "|".join(str(record.get(field) or "UNKNOWN").strip() or "UNKNOWN" for field in fields)


def _safe_rate(numerator: float | int, denominator: float | int) -> float:
    return float(numerator) / max(1.0, float(denominator or 0.0))


def _resolve_outcome_matches(
    decision: Mapping[str, Any],
    *,
    outcomes_by_trade_id: Mapping[str, list[dict[str, Any]]],
    outcomes_by_context: Mapping[str, list[dict[str, Any]]],
    outcomes_by_family_direction: Mapping[str, list[dict[str, Any]]] | None = None,
    outcomes_by_family: Mapping[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    trade_id = str(decision.get("trade_id") or "").strip()
    if trade_id:
        matched = list(outcomes_by_trade_id.get(trade_id) or [])
        if matched:
            return matched
    matched = list(outcomes_by_context.get(_decision_context_key(decision), []) or [])
    if matched:
        return matched
    if outcomes_by_family_direction is not None:
        family_direction_key = "|".join(
            [
                str(decision.get("strategy_family") or "unknown"),
                str(decision.get("direction_family") or "unknown"),
            ]
        )
        matched = list(outcomes_by_family_direction.get(family_direction_key, []) or [])
        if matched:
            return matched
    if outcomes_by_family is not None:
        family_key = str(decision.get("strategy_family") or "unknown")
        matched = list(outcomes_by_family.get(family_key, []) or [])
        if matched:
            return matched
    return []


def _survivor_realized_rs(outcomes: Iterable[Mapping[str, Any]]) -> list[float]:
    survivor_rs: list[float] = []
    fallback_rs: list[float] = []
    for row in outcomes or []:
        realized_r = _safe_float(row.get("realized_r_multiple"))
        if realized_r is None:
            continue
        fallback_rs.append(float(realized_r))
        if not _safe_bool(row.get("rejection_saved_loss")) and not _safe_bool(row.get("rejection_missed_win")):
            survivor_rs.append(float(realized_r))
    return survivor_rs or fallback_rs


def _starvation_survival_floor() -> float:
    legacy_floor = float(getattr(cfg, "OFFLINE_THRESHOLD_AUDIT_SURVIVAL_RATE_FLOOR", 0.25) or 0.25)
    configured = getattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", None)
    if configured in (None, "", "None"):
        return legacy_floor
    return max(legacy_floor, float(configured))


def _impact_dimension_definitions() -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        ("by_stage", ("rejected_at_stage",)),
        ("by_stage_strategy_family", ("rejected_at_stage", "strategy_family")),
        ("by_stage_direction_family", ("rejected_at_stage", "direction_family")),
        ("by_stage_session_mode", ("rejected_at_stage", "session_mode")),
        ("by_stage_strategy_regime_mode", ("rejected_at_stage", "strategy_regime_mode")),
    )


def _group_dimension_definitions() -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        ("strategy_family", ("strategy_family",)),
        ("direction_family", ("direction_family",)),
        ("session_mode", ("session_mode",)),
        ("strategy_regime_mode", ("strategy_regime_mode",)),
        ("strategy_family__session_mode", ("strategy_family", "session_mode")),
        ("strategy_family__strategy_regime_mode", ("strategy_family", "strategy_regime_mode")),
    )


def _dominant_counter(counter: Counter[str]) -> tuple[str | None, float]:
    if not counter:
        return None, 0.0
    label, count = counter.most_common(1)[0]
    return label, _safe_rate(count, sum(counter.values()))


def summarize_rejections_by_stage(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [normalize_candidate_decision(record) for record in (records or [])]
    stage_counter = Counter()
    reason_counter = Counter()
    for row in normalized:
        stage = row.get("rejected_at_stage")
        reason = row.get("rejection_reason_code")
        if stage:
            stage_counter[str(stage)] += 1
        if reason:
            reason_counter[str(reason)] += 1
    total_rejections = sum(stage_counter.values())
    dominant_stage = stage_counter.most_common(1)[0][0] if stage_counter else None
    dominant_share = (
        float(stage_counter.get(dominant_stage, 0)) / max(1, total_rejections)
        if dominant_stage is not None
        else 0.0
    )
    return {
        "rejections_by_stage": dict(stage_counter),
        "rejections_by_reason": dict(reason_counter),
        "total_rejections": int(total_rejections),
        "dominant_rejection_stage": dominant_stage,
        "dominant_rejection_stage_share": round(float(dominant_share), 6),
    }


def summarize_score_distributions(records: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, float | None]]:
    normalized = [normalize_candidate_decision(record) for record in (records or [])]
    fields = (
        "setup_score",
        "trigger_score",
        "entry_quality_score",
        "family_survival_score",
        "priority_score",
        "realized_r_multiple",
    )
    summary: dict[str, dict[str, float | None]] = {}
    for field in fields:
        values = [float(value) for value in (_safe_float(row.get(field)) for row in normalized) if value is not None]
        summary[field] = {
            "p10": _percentile(values, 0.10),
            "p25": _percentile(values, 0.25),
            "p50": _percentile(values, 0.50),
            "p75": _percentile(values, 0.75),
            "p90": _percentile(values, 0.90),
        }
    return summary


def summarize_rejection_impact(
    candidate_decisions: Iterable[Mapping[str, Any]],
    outcome_records: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    decisions = [normalize_candidate_decision(record) for record in (candidate_decisions or [])]
    rejected_rows = [
        row
        for row in decisions
        if row.get("rejected_at_stage")
        and str(row.get("market_mode") or "").strip().upper() in {"SIM", "PAPER", "OFFHOURS"}
    ]
    normalized_outcomes = [_normalize_outcome_record(record) for record in (outcome_records or [])]
    outcomes_by_trade_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outcomes_by_context: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outcomes_by_family_direction: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outcomes_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in normalized_outcomes:
        trade_id = str(row.get("trade_id") or "").strip()
        if trade_id:
            outcomes_by_trade_id[trade_id].append(row)
        outcomes_by_context[_decision_context_key(row)].append(row)
        outcomes_by_family_direction[
            "|".join(
                [
                    str(row.get("strategy_family") or "unknown"),
                    str(row.get("direction_family") or "unknown"),
                ]
            )
        ].append(row)
        outcomes_by_family[str(row.get("strategy_family") or "unknown")].append(row)

    dimension_buckets: dict[str, dict[str, dict[str, Any]]] = {
        name: {}
        for name, _fields in _impact_dimension_definitions()
    }

    for rec in rejected_rows:
        matched = _resolve_outcome_matches(
            rec,
            outcomes_by_trade_id=outcomes_by_trade_id,
            outcomes_by_context=outcomes_by_context,
            outcomes_by_family_direction=outcomes_by_family_direction,
            outcomes_by_family=outcomes_by_family,
        )
        missed_votes = 0
        saved_votes = 0
        for outcome in matched:
            missed, saved = _classify_outcome_vote(outcome)
            missed_votes += 1 if missed else 0
            saved_votes += 1 if saved else 0
        survivor_rs = _survivor_realized_rs(matched)
        for summary_name, fields in _impact_dimension_definitions():
            key = _impact_dimension_key(rec, fields)
            bucket = dimension_buckets[summary_name].setdefault(
                key,
                {
                    field: rec.get(field)
                    for field in {
                        "rejected_at_stage",
                        "strategy_family",
                        "direction_family",
                        "session_mode",
                        "strategy_regime_mode",
                    }
                },
            )
            bucket["reject_count"] = int(bucket.get("reject_count") or 0) + 1
            bucket["matched_outcome_count"] = int(bucket.get("matched_outcome_count") or 0) + len(matched)
            bucket["missed_win_count"] = int(bucket.get("missed_win_count") or 0) + (1 if missed_votes > saved_votes else 0)
            bucket["saved_loss_count"] = int(bucket.get("saved_loss_count") or 0) + (1 if saved_votes > missed_votes else 0)
            bucket.setdefault("_survivor_realized_rs", [])
            bucket["_survivor_realized_rs"].extend(float(value) for value in survivor_rs)

    for bucket_map in dimension_buckets.values():
        for value in bucket_map.values():
            reject_count = int(value.get("reject_count") or 0)
            missed_win_count = int(value.get("missed_win_count") or 0)
            saved_loss_count = int(value.get("saved_loss_count") or 0)
            matched_outcome_count = int(value.get("matched_outcome_count") or 0)
            missed_win_rate = _safe_rate(missed_win_count, reject_count)
            saved_loss_rate = _safe_rate(saved_loss_count, reject_count)
            value["missed_win_rate"] = round(float(missed_win_rate), 6)
            value["saved_loss_rate"] = round(float(saved_loss_rate), 6)
            value["impact_score"] = round(float(missed_win_rate - saved_loss_rate), 6)
            value["coverage_rate"] = round(_safe_rate(matched_outcome_count, reject_count), 6)
            value["median_realized_r_of_survivors_if_available"] = _round_or_none(
                _percentile(list(value.pop("_survivor_realized_rs", [])), 0.50)
            )

    return {
        "version": _AUDIT_VERSION,
        "generated_at": _now_utc_iso(),
        "record_count": len(rejected_rows),
        **dimension_buckets,
    }


def rank_rejection_impact(
    candidate_decisions: Iterable[Mapping[str, Any]],
    outcome_records: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    summary = summarize_rejection_impact(candidate_decisions, outcome_records)
    by_stage_family = dict(summary.get("by_stage_strategy_family") or {})
    impact: dict[str, dict[str, Any]] = {}
    min_samples = max(1, int(getattr(cfg, "OFFLINE_THRESHOLD_LEARNING_MIN_SAMPLES", 20) or 20))
    for key, value in by_stage_family.items():
        stage = str(value.get("rejected_at_stage") or "unknown").strip().lower() or "unknown"
        family = str(value.get("strategy_family") or "unknown").strip().lower() or "unknown"
        reject_count = int(value.get("reject_count") or 0)
        matched_outcome_count = int(value.get("matched_outcome_count") or 0)
        raw_score = float(value.get("impact_score") or 0.0)
        coverage = _safe_rate(matched_outcome_count, reject_count)
        shrinkage = float(reject_count) / float(reject_count + min_samples)
        impact_confidence = max(0.0, min(1.0, coverage * shrinkage))
        impact_score = max(-1.0, min(1.0, raw_score * impact_confidence))
        impact[f"{stage}:{family}"] = {
            "rejected_at_stage": stage,
            "strategy_family": family,
            "count": reject_count,
            "missed_win": int(value.get("missed_win_count") or 0),
            "saved_loss": int(value.get("saved_loss_count") or 0),
            "matched_outcome_count": matched_outcome_count,
            "impact_score": round(float(impact_score), 6),
            "impact_confidence": round(float(impact_confidence), 6),
            "learning_applied": bool(reject_count >= min_samples and matched_outcome_count > 0),
        }
    return impact


def _rate_by_dimension(records: list[dict[str, Any]], field: str) -> dict[str, dict[str, float | int]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        key = str(row.get(field) or "UNKNOWN").strip() or "UNKNOWN"
        buckets[key].append(row)
    summary: dict[str, dict[str, float | int]] = {}
    for key, bucket in buckets.items():
        survived = sum(1 for row in bucket if not row.get("rejected_at_stage"))
        summary[key] = {
            "raw_candidates": int(len(bucket)),
            "survived_candidates": int(survived),
            "survival_rate": round(float(survived) / max(1, len(bucket)), 6),
        }
    return summary


def compute_starvation_diagnostics(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [normalize_candidate_decision(record) for record in (records or [])]
    raw_candidate_count = len(normalized)
    if raw_candidate_count <= 0:
        return {
            "raw_candidate_count": 0,
            "surviving_candidate_count": 0,
            "survival_rate": 0.0,
            "executable_rate": 0.0,
            "advisory_rate": 0.0,
            "no_trade_rate": 1.0,
            "top_family_share": 0.0,
            "starvation_flag": True,
            "starvation_reason": "no_candidates",
        }
    surviving = [row for row in normalized if not row.get("rejected_at_stage")]
    selected = [row for row in normalized if bool(row.get("selected_for_execution"))]
    advisory = [
        row
        for row in normalized
        if str(row.get("candidate_class") or "").strip().upper() == "ADVISORY_ONLY"
    ]
    family_counts = Counter(str(row.get("direction_family") or "unknown") for row in (surviving or normalized))
    top_family_share = (
        float(family_counts.most_common(1)[0][1]) / max(1, len(surviving or normalized))
        if family_counts
        else 0.0
    )
    rejections = summarize_rejections_by_stage(normalized)
    survival_rate = float(len(surviving)) / max(1, raw_candidate_count)
    executable_rate = float(len(selected)) / max(1, raw_candidate_count)
    advisory_rate = float(len(advisory)) / max(1, raw_candidate_count)
    no_trade_rate = 1.0 if not selected else 0.0
    survival_floor = _starvation_survival_floor()
    top_family_share_warn = float(getattr(cfg, "OFFLINE_THRESHOLD_AUDIT_TOP_FAMILY_SHARE_WARN", 0.75) or 0.75)
    stage_cluster_warn = float(getattr(cfg, "OFFLINE_THRESHOLD_AUDIT_STAGE_CLUSTER_WARN", 0.60) or 0.60)
    starvation_reason = None
    if no_trade_rate >= 1.0 and raw_candidate_count > 0:
        starvation_reason = "no_executable_candidates"
    elif survival_rate < survival_floor:
        starvation_reason = "survival_rate_below_floor"
    elif top_family_share >= top_family_share_warn:
        starvation_reason = "family_dominance"
    elif float(rejections.get("dominant_rejection_stage_share") or 0.0) >= stage_cluster_warn:
        starvation_reason = "threshold_cluster"
    starvation_flag = starvation_reason is not None
    return {
        "raw_candidate_count": int(raw_candidate_count),
        "surviving_candidate_count": int(len(surviving)),
        "survival_rate": round(float(survival_rate), 6),
        "executable_rate": round(float(executable_rate), 6),
        "advisory_rate": round(float(advisory_rate), 6),
        "no_trade_rate": round(float(no_trade_rate), 6),
        "top_family_share": round(float(top_family_share), 6),
        "starvation_flag": bool(starvation_flag),
        "starvation_reason": starvation_reason,
    }


def _summarize_starvation_bucket(bucket: list[dict[str, Any]]) -> dict[str, Any]:
    raw_candidate_count = len(bucket)
    surviving = [row for row in bucket if not row.get("rejected_at_stage")]
    selected = [row for row in bucket if bool(row.get("selected_for_execution"))]
    advisory = [
        row
        for row in bucket
        if str(row.get("candidate_class") or "").strip().upper() == "ADVISORY_ONLY"
    ]
    batches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in bucket:
        batch_key = str(row.get("decision_batch_id") or row.get("decision_scope") or "unknown")
        batches[batch_key].append(row)
    no_trade_batches = sum(
        1
        for rows in batches.values()
        if not any(bool(row.get("selected_for_execution")) for row in rows)
    )
    no_trade_rate = _safe_rate(no_trade_batches, len(batches) or 1)
    family_counts = Counter(str(row.get("direction_family") or "unknown") for row in (surviving or bucket))
    top_family_share = 0.0
    if family_counts:
        top_family_share = _safe_rate(family_counts.most_common(1)[0][1], len(surviving or bucket))
    survival_rate = _safe_rate(len(surviving), raw_candidate_count)
    executable_rate = _safe_rate(len(selected), raw_candidate_count)
    advisory_rate = _safe_rate(len(advisory), raw_candidate_count)
    survival_floor = _starvation_survival_floor()
    top_family_share_warn = float(getattr(cfg, "OFFLINE_THRESHOLD_AUDIT_TOP_FAMILY_SHARE_WARN", 0.75) or 0.75)
    no_trade_warn = float(getattr(cfg, "OFFLINE_THRESHOLD_AUDIT_NO_EXECUTABLE_RATE_WARN", 0.70) or 0.70)
    starvation_reason = None
    if no_trade_rate >= no_trade_warn and raw_candidate_count > 0:
        starvation_reason = "no_trade_rate_high"
    elif survival_rate < survival_floor:
        starvation_reason = "survival_rate_below_floor"
    elif top_family_share >= top_family_share_warn:
        starvation_reason = "family_dominance"
    return {
        "raw_candidate_count": int(raw_candidate_count),
        "survived_candidate_count": int(len(surviving)),
        "survival_rate": round(float(survival_rate), 6),
        "executable_rate": round(float(executable_rate), 6),
        "advisory_rate": round(float(advisory_rate), 6),
        "no_trade_rate": round(float(no_trade_rate), 6),
        "top_family_share": round(float(top_family_share), 6),
        "starvation_flag": bool(starvation_reason is not None),
        "starvation_reason": starvation_reason,
    }


def summarize_starvation_by_group(candidate_decisions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    decisions = [normalize_candidate_decision(record) for record in (candidate_decisions or [])]
    selector_decisions = [row for row in decisions if row.get("decision_phase") == "selector"] or list(decisions)
    grouped: dict[str, dict[str, dict[str, Any]]] = {
        name: {}
        for name, _fields in _group_dimension_definitions()
    }
    for summary_name, fields in _group_dimension_definitions():
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in selector_decisions:
            buckets[_impact_dimension_key(row, fields)].append(row)
        for key, bucket in buckets.items():
            item = _summarize_starvation_bucket(bucket)
            for field in fields:
                item[field] = bucket[0].get(field)
            grouped[summary_name][key] = item
    return {
        "version": _AUDIT_VERSION,
        "generated_at": _now_utc_iso(),
        "record_count": len(selector_decisions),
        **grouped,
    }


def summarize_threshold_behavior(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [normalize_candidate_decision(record) for record in (records or [])]
    selector_records = [row for row in normalized if row.get("decision_phase") == "selector"] or list(normalized)
    stage_summary = summarize_rejections_by_stage(selector_records)
    score_summary = summarize_score_distributions(selector_records)
    batches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selector_records:
        batches[str(row.get("decision_batch_id") or row.get("decision_scope") or "unknown")].append(row)
    batch_summaries = [compute_starvation_diagnostics(batch) for batch in batches.values()]
    selector_outcome_counter = Counter()
    for batch in batches.values():
        outcome = next((row.get("selector_outcome") for row in batch if row.get("selector_outcome")), None)
        if outcome:
            selector_outcome_counter[str(outcome)] += 1
    batch_count = len(batch_summaries)
    no_exec_rate = float(selector_outcome_counter.get("NO_EXECUTABLE_OPPORTUNITY", 0)) / max(1, batch_count)
    advisory_only_rate = float(selector_outcome_counter.get("ADVISORY_ONLY", 0)) / max(1, batch_count)
    avg_survival_rate = (
        sum(float(item.get("survival_rate") or 0.0) for item in batch_summaries) / max(1, batch_count)
        if batch_summaries
        else 0.0
    )
    avg_no_trade_rate = (
        sum(float(item.get("no_trade_rate") or 0.0) for item in batch_summaries) / max(1, batch_count)
        if batch_summaries
        else 0.0
    )
    warning_threshold_cluster = bool(
        float(stage_summary.get("dominant_rejection_stage_share") or 0.0)
        >= float(getattr(cfg, "OFFLINE_THRESHOLD_AUDIT_STAGE_CLUSTER_WARN", 0.60) or 0.60)
    )
    warning_engine_too_timid = bool(
        avg_survival_rate < _starvation_survival_floor()
        or no_exec_rate >= float(getattr(cfg, "OFFLINE_THRESHOLD_AUDIT_NO_EXECUTABLE_RATE_WARN", 0.70) or 0.70)
    )
    warning_family_starvation = any(bool(item.get("starvation_reason") == "family_dominance") for item in batch_summaries)
    return {
        "version": _AUDIT_VERSION,
        "generated_at": _now_utc_iso(),
        "record_count": len(selector_records),
        **stage_summary,
        "score_distributions": score_summary,
        "selector_outcome_counts": dict(selector_outcome_counter),
        "selector_outcome_rates": {
            key: round(float(value) / max(1, batch_count), 6)
            for key, value in selector_outcome_counter.items()
        },
        "batch_count": int(batch_count),
        "avg_survival_rate": round(float(avg_survival_rate), 6),
        "avg_no_trade_rate": round(float(avg_no_trade_rate), 6),
        "no_executable_opportunity_rate": round(float(no_exec_rate), 6),
        "advisory_only_rate": round(float(advisory_only_rate), 6),
        "survival_rate_by_family": _rate_by_dimension(selector_records, "direction_family"),
        "survival_rate_by_session": _rate_by_dimension(selector_records, "session_mode"),
        "survival_rate_by_regime": _rate_by_dimension(selector_records, "strategy_regime_mode"),
        "warning_engine_too_timid": warning_engine_too_timid,
        "warning_family_starvation": warning_family_starvation,
        "warning_threshold_cluster": warning_threshold_cluster,
    }


def summarize_survival_vs_expectancy(
    candidate_decisions: Iterable[Mapping[str, Any]],
    outcome_records: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    decisions = [normalize_candidate_decision(record) for record in (candidate_decisions or [])]
    selector_decisions = [row for row in decisions if row.get("decision_phase") == "selector"] or list(decisions)
    outcome_rows: list[dict[str, Any]] = []
    for record in (outcome_records or []):
        item = dict(record or {})
        outcome_rows.append(
            {
                "strategy_family": str(item.get("strategy_family") or "unknown").strip().lower() or "unknown",
                "direction_family": str(item.get("direction_family") or "unknown").strip().lower() or "unknown",
                "strategy_regime_mode": str(item.get("strategy_regime_mode") or "UNKNOWN").strip().upper() or "UNKNOWN",
                "session_mode": str(item.get("session_mode") or "UNKNOWN").strip().upper() or "UNKNOWN",
                "simulated_pnl": _safe_float(item.get("simulated_pnl")),
                "mfe": _safe_float(item.get("mfe")),
                "mae": _safe_float(item.get("mae")),
                "realized_r_multiple": _safe_float(item.get("realized_r_multiple")),
                "rejection_saved_loss": _safe_bool(item.get("rejection_saved_loss")),
                "rejection_missed_win": _safe_bool(item.get("rejection_missed_win")),
            }
        )
    grouped_decisions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_outcomes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selector_decisions:
        key = "|".join(
            [
                str(row.get("strategy_family") or "unknown"),
                str(row.get("direction_family") or "unknown"),
                str(row.get("strategy_regime_mode") or "UNKNOWN"),
                str(row.get("session_mode") or "UNKNOWN"),
            ]
        )
        grouped_decisions[key].append(row)
    for row in outcome_rows:
        key = "|".join(
            [
                str(row.get("strategy_family") or "unknown"),
                str(row.get("direction_family") or "unknown"),
                str(row.get("strategy_regime_mode") or "UNKNOWN"),
                str(row.get("session_mode") or "UNKNOWN"),
            ]
        )
        grouped_outcomes[key].append(row)
    groups: dict[str, dict[str, Any]] = {}
    survival_floor = _starvation_survival_floor()
    min_r_delta = float(getattr(cfg, "OFFLINE_EDGE_IMPROVEMENT_MIN_R_DELTA", 0.05) or 0.05)
    filtering_warn_enabled = bool(getattr(cfg, "OFFLINE_FILTERING_WITHOUT_EDGE_WARN", True))
    any_filtering_no_edge = False
    for key, bucket in grouped_decisions.items():
        outcomes = grouped_outcomes.get(key, [])
        raw_candidates = len(bucket)
        survived_candidates = sum(1 for row in bucket if not row.get("rejected_at_stage"))
        survival_rate = float(survived_candidates) / max(1, raw_candidates)
        pnls = [float(row["simulated_pnl"]) for row in outcomes if row.get("simulated_pnl") is not None]
        mfes = [float(row["mfe"]) for row in outcomes if row.get("mfe") is not None]
        maes = [float(row["mae"]) for row in outcomes if row.get("mae") is not None]
        realized_rs = [float(row["realized_r_multiple"]) for row in outcomes if row.get("realized_r_multiple") is not None]
        rejection_saved_loss_rate = (
            sum(1 for row in outcomes if bool(row.get("rejection_saved_loss"))) / max(1, len(outcomes))
            if outcomes
            else 0.0
        )
        rejection_missed_win_rate = (
            sum(1 for row in outcomes if bool(row.get("rejection_missed_win"))) / max(1, len(outcomes))
            if outcomes
            else 0.0
        )
        median_pnl = _percentile(pnls, 0.50)
        median_mfe = _percentile(mfes, 0.50)
        median_mae = _percentile(maes, 0.50)
        median_realized_r_multiple = _percentile(realized_rs, 0.50)
        survival_rate_down = bool(survival_rate < survival_floor)
        median_realized_r_up = bool(
            median_realized_r_multiple is not None
            and float(median_realized_r_multiple) >= min_r_delta
        )
        edge_improved = bool(survival_rate_down and median_realized_r_up)
        filtering_without_edge_improvement = bool(
            filtering_warn_enabled
            and survival_rate_down
            and not median_realized_r_up
            and raw_candidates > 0
        )
        any_filtering_no_edge = any_filtering_no_edge or filtering_without_edge_improvement
        strategy_family, direction_family, strategy_regime_mode, session_mode = key.split("|", 3)
        groups[key] = {
            "strategy_family": strategy_family,
            "direction_family": direction_family,
            "strategy_regime_mode": strategy_regime_mode,
            "session_mode": session_mode,
            "raw_candidates": int(raw_candidates),
            "survived_candidates": int(survived_candidates),
            "survival_rate": round(float(survival_rate), 6),
            "median_simulated_pnl": round(float(median_pnl), 6) if median_pnl is not None else None,
            "median_mfe": round(float(median_mfe), 6) if median_mfe is not None else None,
            "median_mae": round(float(median_mae), 6) if median_mae is not None else None,
            "median_realized_r_multiple": round(float(median_realized_r_multiple), 6) if median_realized_r_multiple is not None else None,
            "saved_loss_rate": round(float(rejection_saved_loss_rate), 6),
            "missed_win_rate": round(float(rejection_missed_win_rate), 6),
            "rejection_saved_loss_rate": round(float(rejection_saved_loss_rate), 6),
            "rejection_missed_win_rate": round(float(rejection_missed_win_rate), 6),
            "edge_improved_flag": edge_improved,
            "filtering_without_edge_flag": filtering_without_edge_improvement,
            "edge_improved_under_strict_filter": edge_improved,
            "filtering_without_edge_improvement": filtering_without_edge_improvement,
        }
    return {
        "version": _AUDIT_VERSION,
        "generated_at": _now_utc_iso(),
        "groups": groups,
        "warning_filtering_without_edge_improvement": any_filtering_no_edge,
    }


def summarize_top_damaging_gates(
    candidate_decisions: Iterable[Mapping[str, Any]],
    outcome_records: Iterable[Mapping[str, Any]],
    top_n: int = 3,
) -> dict[str, Any]:
    decisions = [normalize_candidate_decision(record) for record in (candidate_decisions or [])]
    rejected_rows = [row for row in decisions if row.get("rejected_at_stage")]
    impact_summary = summarize_rejection_impact(decisions, outcome_records)
    stage_family = dict(impact_summary.get("by_stage_strategy_family") or {})
    ranked_rows = sorted(
        (
            (key, dict(value))
            for key, value in stage_family.items()
            if float((value or {}).get("impact_score") or 0.0) > 0.0
        ),
        key=lambda item: (
            -float(item[1].get("impact_score") or 0.0),
            -int(item[1].get("reject_count") or 0),
            item[0],
        ),
    )
    top_limit = max(1, int(top_n or 1))
    top_rows: list[dict[str, Any]] = []
    for rank, (key, value) in enumerate(ranked_rows[:top_limit], start=1):
        stage = str(value.get("rejected_at_stage") or "unknown").strip().lower() or "unknown"
        family = str(value.get("strategy_family") or "unknown").strip().lower() or "unknown"
        bucket = [
            row
            for row in rejected_rows
            if str(row.get("rejected_at_stage") or "").strip().lower() == stage
            and str(row.get("strategy_family") or "unknown").strip().lower() == family
        ]
        direction_counts = Counter(str(row.get("direction_family") or "unknown") for row in bucket)
        session_counts = Counter(str(row.get("session_mode") or "UNKNOWN") for row in bucket)
        regime_counts = Counter(str(row.get("strategy_regime_mode") or "UNKNOWN") for row in bucket)
        dominant_direction_family, dominant_direction_share = _dominant_counter(direction_counts)
        dominant_session_mode, dominant_session_share = _dominant_counter(session_counts)
        dominant_strategy_regime_mode, dominant_regime_share = _dominant_counter(regime_counts)
        top_rows.append(
            {
                "rank": int(rank),
                "gate_key": key,
                "rejected_at_stage": stage,
                "strategy_family": family,
                "reject_count": int(value.get("reject_count") or 0),
                "missed_win_rate": round(float(value.get("missed_win_rate") or 0.0), 6),
                "saved_loss_rate": round(float(value.get("saved_loss_rate") or 0.0), 6),
                "impact_score": round(float(value.get("impact_score") or 0.0), 6),
                "median_realized_r_of_survivors_if_available": _round_or_none(
                    _safe_float(value.get("median_realized_r_of_survivors_if_available"))
                ),
                "dominant_direction_family": dominant_direction_family,
                "dominant_direction_family_share": round(float(dominant_direction_share), 6),
                "dominant_session_mode": dominant_session_mode,
                "dominant_session_mode_share": round(float(dominant_session_share), 6),
                "dominant_strategy_regime_mode": dominant_strategy_regime_mode,
                "dominant_strategy_regime_mode_share": round(float(dominant_regime_share), 6),
            }
        )
    return {
        "version": _AUDIT_VERSION,
        "generated_at": _now_utc_iso(),
        "top_n": int(top_limit),
        "gates": top_rows,
    }


def write_threshold_audit_summaries(
    *,
    candidate_decisions: Iterable[Mapping[str, Any]] | None = None,
    outcome_records: Iterable[Mapping[str, Any]] | None = None,
    summary_path: str | Path | None = None,
    survival_path: str | Path | None = None,
) -> dict[str, Any]:
    decisions = list(candidate_decisions) if candidate_decisions is not None else load_candidate_decisions()
    outcomes = list(outcome_records) if outcome_records is not None else load_outcome_records()
    threshold_summary = summarize_threshold_behavior(decisions)
    survival_summary = summarize_survival_vs_expectancy(decisions, outcomes)
    rejection_impact_summary = summarize_rejection_impact(decisions, outcomes)
    starvation_by_group_summary = summarize_starvation_by_group(decisions)
    top_damaging_gates = summarize_top_damaging_gates(
        decisions,
        outcomes,
        top_n=int(getattr(cfg, "OFFLINE_REJECTION_IMPACT_TOP_N", 3) or 3),
    )
    threshold_impact = rank_rejection_impact(decisions, outcomes)
    write_json_atomic(
        Path(summary_path).expanduser() if summary_path is not None else threshold_audit_summary_path(),
        threshold_summary,
    )
    write_json_atomic(
        Path(survival_path).expanduser() if survival_path is not None else survival_expectancy_summary_path(),
        survival_summary,
    )
    if bool(getattr(cfg, "OFFLINE_REJECTION_IMPACT_ENABLE", True)):
        write_json_atomic(rejection_impact_summary_path(), rejection_impact_summary)
        write_json_atomic(starvation_by_group_summary_path(), starvation_by_group_summary)
        write_json_atomic(top_damaging_gates_path(), top_damaging_gates)
    save_threshold_impact(threshold_impact)
    return {
        "threshold_summary": threshold_summary,
        "survival_expectancy_summary": survival_summary,
        "rejection_impact_summary": rejection_impact_summary,
        "starvation_by_group_summary": starvation_by_group_summary,
        "top_damaging_gates": top_damaging_gates,
        "threshold_impact": threshold_impact,
    }

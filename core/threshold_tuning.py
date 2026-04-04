from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from config import config as cfg
from core.events import write_json_atomic
from core.threshold_audit import (
    rejection_impact_summary_path,
    starvation_by_group_summary_path,
    survival_expectancy_summary_path,
    threshold_audit_dir,
    top_damaging_gates_path,
)


_TUNING_VERSION = 1
_HARD_PROTECT_STAGES = {"risk_budget", "portfolio_heat", "kill_switch"}
_ADJUSTABLE_STAGES = {"setup", "trigger", "entry_quality", "family_survival"}


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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def threshold_tuning_recommendations_path() -> Path:
    return threshold_audit_dir() / "threshold_tuning_recommendations.json"


def _load_json_dict(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    target = Path(path).expanduser()
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload or {}) if isinstance(payload, Mapping) else {}


def load_threshold_tuning_inputs() -> dict[str, Any]:
    return {
        "rejection_impact_summary": _load_json_dict(rejection_impact_summary_path()),
        "starvation_by_group_summary": _load_json_dict(starvation_by_group_summary_path()),
        "survival_expectancy_summary": _load_json_dict(survival_expectancy_summary_path()),
        "top_damaging_gates": _load_json_dict(top_damaging_gates_path()),
    }


def load_threshold_tuning_recommendations(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else threshold_tuning_recommendations_path()
    return _load_json_dict(target)


def save_threshold_tuning_recommendations(
    recommendations: Mapping[str, Any],
    *,
    path: str | Path | None = None,
) -> Path:
    target = Path(path).expanduser() if path is not None else threshold_tuning_recommendations_path()
    payload = {
        "version": _TUNING_VERSION,
        "generated_at": _now_utc_iso(),
        **dict(recommendations or {}),
    }
    write_json_atomic(target, payload)
    return target


def should_protect_gate(gate_metrics: Mapping[str, Any]) -> bool:
    stage = str((gate_metrics or {}).get("rejected_at_stage") or "").strip().lower()
    saved_loss_rate = float(
        _safe_float((gate_metrics or {}).get("saved_loss_rate"))
        or 0.0
    )
    protect_floor = float(
        getattr(cfg, "OFFLINE_THRESHOLD_TUNING_PROTECT_SAVED_LOSS_RATE", 0.40) or 0.40
    )
    if stage in _HARD_PROTECT_STAGES:
        return True
    return bool(saved_loss_rate >= protect_floor)


def _protection_reason(gate_metrics: Mapping[str, Any]) -> str:
    stage = str((gate_metrics or {}).get("rejected_at_stage") or "").strip().lower()
    if stage in _HARD_PROTECT_STAGES:
        return "hard_risk_gate"
    return "saved_loss_rate_high"


def get_contextual_threshold_adjustment(
    stage: str | None,
    family: str | None,
    session: str | None,
    regime: str | None,
    recommendations: Mapping[str, Any] | None,
) -> float:
    adjustments = ((recommendations or {}).get("recommended_contextual_adjustments") or {})
    if not isinstance(adjustments, Mapping):
        return 0.0
    key = "|".join(
        [
            str(stage or "unknown").strip().lower() or "unknown",
            str(family or "unknown").strip().lower() or "unknown",
            str(session or "UNKNOWN").strip().upper() or "UNKNOWN",
            str(regime or "UNKNOWN").strip().upper() or "UNKNOWN",
        ]
    )
    item = adjustments.get(key) or {}
    if not isinstance(item, Mapping):
        return 0.0
    return float(_safe_float(item.get("recommended_delta")) or 0.0)


def _protected_gate_key(stage: str | None, family: str | None) -> str:
    return "|".join(
        [
            str(stage or "unknown").strip().lower() or "unknown",
            str(family or "unknown").strip().lower() or "unknown",
        ]
    )


def _gate_entry(key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(payload or {})
    item.setdefault("gate_key", key)
    item["rejected_at_stage"] = str(item.get("rejected_at_stage") or "unknown").strip().lower() or "unknown"
    item["strategy_family"] = str(item.get("strategy_family") or "unknown").strip().lower() or "unknown"
    item["direction_family"] = str(item.get("direction_family") or "unknown").strip().lower() or "unknown"
    item["session_mode"] = str(item.get("session_mode") or "UNKNOWN").strip().upper() or "UNKNOWN"
    item["strategy_regime_mode"] = str(item.get("strategy_regime_mode") or "UNKNOWN").strip().upper() or "UNKNOWN"
    item["impact_score"] = float(_safe_float(item.get("impact_score")) or 0.0)
    item["saved_loss_rate"] = float(_safe_float(item.get("saved_loss_rate")) or 0.0)
    item["missed_win_rate"] = float(_safe_float(item.get("missed_win_rate")) or 0.0)
    item["reject_count"] = int(_safe_int(item.get("reject_count")) or 0)
    return item


def _starvation_entry(group_type: str, key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(payload or {})
    item["group_type"] = str(group_type)
    item["group_key"] = str(key)
    item["survival_rate"] = float(_safe_float(item.get("survival_rate")) or 0.0)
    item["no_trade_rate"] = float(_safe_float(item.get("no_trade_rate")) or 0.0)
    item["raw_candidate_count"] = int(_safe_int(item.get("raw_candidate_count")) or 0)
    item["survived_candidate_count"] = int(_safe_int(item.get("survived_candidate_count")) or 0)
    item["starvation_flag"] = bool(item.get("starvation_flag", False))
    item["starvation_reason"] = str(item.get("starvation_reason") or "").strip().lower() or None
    return item


def _recommendation_delta(impact_score: float, survival_rate: float) -> float:
    max_delta = abs(float(getattr(cfg, "OFFLINE_THRESHOLD_TUNING_MAX_DELTA", 0.03) or 0.03))
    starvation_floor = float(getattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", 0.25) or 0.25)
    starvation_gap = max(0.0, starvation_floor - float(survival_rate))
    raw = min(max_delta, 0.01 + (max(0.0, float(impact_score)) * 0.03) + (starvation_gap * 0.05))
    if raw <= 0.0:
        return 0.0
    if raw <= 0.02 or max_delta <= 0.02:
        return -min(max_delta, 0.02)
    if raw <= 0.03 or max_delta <= 0.03:
        return -min(max_delta, 0.03)
    return -min(max_delta, 0.05)


def build_threshold_tuning_recommendations(
    *,
    rejection_impact_summary: Mapping[str, Any],
    starvation_by_group_summary: Mapping[str, Any],
    survival_expectancy_summary: Mapping[str, Any],
    top_damaging_gates: Mapping[str, Any],
) -> dict[str, Any]:
    min_impact_score = float(
        getattr(cfg, "OFFLINE_THRESHOLD_TUNING_MIN_IMPACT_SCORE", 0.20) or 0.20
    )
    top_n = max(1, int(getattr(cfg, "OFFLINE_REJECTION_IMPACT_TOP_N", 3) or 3))
    stage_family_map = dict((rejection_impact_summary or {}).get("by_stage_strategy_family") or {})
    survival_groups = dict((survival_expectancy_summary or {}).get("groups") or {})
    starvation_groups: list[dict[str, Any]] = []
    for group_type in (
        "strategy_family",
        "direction_family",
        "session_mode",
        "strategy_regime_mode",
        "strategy_family__session_mode",
        "strategy_family__strategy_regime_mode",
    ):
        group_map = dict((starvation_by_group_summary or {}).get(group_type) or {})
        for key, value in group_map.items():
            starvation_groups.append(_starvation_entry(group_type, key, value))
    starvation_groups.sort(
        key=lambda item: (
            not bool(item.get("starvation_flag", False)),
            float(item.get("survival_rate") or 0.0),
            -int(item.get("raw_candidate_count") or 0),
            str(item.get("group_key") or ""),
        )
    )

    protective_candidates: list[dict[str, Any]] = []
    loosening_candidates: list[dict[str, Any]] = []
    protected_gate_map: dict[str, dict[str, Any]] = {}
    for key, value in stage_family_map.items():
        item = _gate_entry(key, value)
        if should_protect_gate(item):
            protection_reason = _protection_reason(item)
            enriched = {
                **item,
                "protection_reason": protection_reason,
                "gate_protected_flag": True,
            }
            protective_candidates.append(enriched)
            protected_gate_map[_protected_gate_key(item.get("rejected_at_stage"), item.get("strategy_family"))] = {
                "gate_protected_flag": True,
                "protection_reason": protection_reason,
                "saved_loss_rate": round(float(item.get("saved_loss_rate") or 0.0), 6),
            }
            continue
        if (
            float(item.get("impact_score") or 0.0) >= min_impact_score
            and float(item.get("missed_win_rate") or 0.0) > float(item.get("saved_loss_rate") or 0.0)
        ):
            loosening_candidates.append({**item, "gate_protected_flag": False})
    loosening_candidates.sort(
        key=lambda item: (
            -float(item.get("impact_score") or 0.0),
            -int(item.get("reject_count") or 0),
            str(item.get("gate_key") or ""),
        )
    )
    protective_candidates.sort(
        key=lambda item: (
            -float(item.get("saved_loss_rate") or 0.0),
            float(item.get("impact_score") or 0.0),
            -int(item.get("reject_count") or 0),
            str(item.get("gate_key") or ""),
        )
    )

    edge_improved_groups: list[dict[str, Any]] = []
    filtering_without_edge_groups: list[dict[str, Any]] = []
    for key, value in survival_groups.items():
        item = dict(value or {})
        item["group_key"] = str(key)
        if bool(item.get("edge_improved_flag", False)):
            edge_improved_groups.append(item)
        if bool(item.get("filtering_without_edge_flag", False)):
            filtering_without_edge_groups.append(item)
    edge_improved_groups.sort(
        key=lambda item: (
            float(item.get("survival_rate") or 0.0),
            -float(_safe_float(item.get("median_realized_r_multiple")) or 0.0),
            str(item.get("group_key") or ""),
        )
    )
    filtering_without_edge_groups.sort(
        key=lambda item: (
            float(item.get("survival_rate") or 0.0),
            float(_safe_float(item.get("median_realized_r_multiple")) or 0.0),
            str(item.get("group_key") or ""),
        )
    )

    recommended_contextual_adjustments: dict[str, dict[str, Any]] = {}
    if bool(getattr(cfg, "OFFLINE_THRESHOLD_TUNING_STARVATION_RELIEF_ENABLE", True)):
        top_damaging_list = list((top_damaging_gates or {}).get("gates") or [])
        for item in filtering_without_edge_groups:
            family = str(item.get("strategy_family") or "unknown").strip().lower() or "unknown"
            session_mode = str(item.get("session_mode") or "UNKNOWN").strip().upper() or "UNKNOWN"
            strategy_regime_mode = str(item.get("strategy_regime_mode") or "UNKNOWN").strip().upper() or "UNKNOWN"
            family_session_key = f"{family}|{session_mode}"
            family_regime_key = f"{family}|{strategy_regime_mode}"
            family_session_group = dict((starvation_by_group_summary or {}).get("strategy_family__session_mode", {}).get(family_session_key) or {})
            family_regime_group = dict((starvation_by_group_summary or {}).get("strategy_family__strategy_regime_mode", {}).get(family_regime_key) or {})
            if not (
                bool(family_session_group.get("starvation_flag", False))
                or bool(family_regime_group.get("starvation_flag", False))
            ):
                continue
            matching_gate = next(
                (
                    gate
                    for gate in top_damaging_list
                    if str(gate.get("strategy_family") or "unknown").strip().lower() == family
                    and not should_protect_gate(gate)
                ),
                None,
            )
            candidate_stage = str((matching_gate or {}).get("rejected_at_stage") or "family_survival").strip().lower() or "family_survival"
            if candidate_stage not in _ADJUSTABLE_STAGES:
                candidate_stage = "family_survival"
            impact_score = float(_safe_float((matching_gate or {}).get("impact_score")) or min_impact_score)
            delta = _recommendation_delta(impact_score, float(item.get("survival_rate") or 0.0))
            if delta == 0.0:
                continue
            confidence = _clamp(
                0.35
                + (min(1.0, impact_score) * 0.35)
                + min(0.30, max(0.0, float(getattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", 0.25) or 0.25) - float(item.get("survival_rate") or 0.0))),
                0.0,
                1.0,
            )
            key = "|".join([candidate_stage, family, session_mode, strategy_regime_mode])
            recommended_contextual_adjustments[key] = {
                "stage": candidate_stage,
                "strategy_family": family,
                "session_mode": session_mode,
                "strategy_regime_mode": strategy_regime_mode,
                "recommended_delta": round(float(delta), 6),
                "reason": "starvation_without_edge_improvement",
                "confidence": round(float(confidence), 6),
            }

    return {
        "version": _TUNING_VERSION,
        "generated_at": _now_utc_iso(),
        "top_damaging_gates": list((top_damaging_gates or {}).get("gates") or [])[:top_n],
        "top_protective_gates": protective_candidates[:top_n],
        "gates_to_loosen": loosening_candidates[:top_n],
        "gates_to_protect": protective_candidates[:top_n],
        "starvation_groups": [item for item in starvation_groups if bool(item.get("starvation_flag", False))][:top_n],
        "edge_improved_groups": edge_improved_groups[:top_n],
        "filtering_without_edge_groups": filtering_without_edge_groups[:top_n],
        "recommended_contextual_adjustments": recommended_contextual_adjustments,
        "protected_gate_map": protected_gate_map,
    }


def rebuild_threshold_tuning_recommendations() -> dict[str, Any]:
    inputs = load_threshold_tuning_inputs()
    recommendations = build_threshold_tuning_recommendations(**inputs)
    save_threshold_tuning_recommendations(recommendations)
    return recommendations

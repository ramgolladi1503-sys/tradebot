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


_TRIAGE_VERSION = 1
_HARD_PROTECT_STAGES = {"risk_budget", "portfolio_heat", "kill_switch"}
_ADJUSTABLE_STAGES = {"trigger", "entry_quality", "family_survival"}


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def threshold_tuning_shortlist_path() -> Path:
    return threshold_audit_dir() / "threshold_tuning_shortlist.json"


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


def load_threshold_triage_inputs() -> dict[str, Any]:
    return {
        "rejection_impact_summary": _load_json_dict(rejection_impact_summary_path()),
        "starvation_by_group_summary": _load_json_dict(starvation_by_group_summary_path()),
        "survival_expectancy_summary": _load_json_dict(survival_expectancy_summary_path()),
        "top_damaging_gates": _load_json_dict(top_damaging_gates_path()),
    }


def load_threshold_tuning_shortlist(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else threshold_tuning_shortlist_path()
    return _load_json_dict(target)


def save_threshold_tuning_shortlist(
    shortlist: Mapping[str, Any],
    *,
    path: str | Path | None = None,
) -> Path:
    target = Path(path).expanduser() if path is not None else threshold_tuning_shortlist_path()
    payload = {
        "version": _TRIAGE_VERSION,
        "generated_at": _now_utc_iso(),
        **dict(shortlist or {}),
    }
    write_json_atomic(target, payload)
    return target


def should_protect_gate(gate_metrics: Mapping[str, Any]) -> bool:
    stage = str((gate_metrics or {}).get("rejected_at_stage") or "").strip().lower()
    if stage in _HARD_PROTECT_STAGES:
        return True
    saved_loss_rate = float(_safe_float((gate_metrics or {}).get("saved_loss_rate")) or 0.0)
    protect_floor = float(
        getattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_PROTECT_SAVED_LOSS_RATE", 0.40) or 0.40
    )
    return bool(saved_loss_rate >= protect_floor)


def _protection_reason(gate_metrics: Mapping[str, Any]) -> str:
    stage = str((gate_metrics or {}).get("rejected_at_stage") or "").strip().lower()
    if stage in _HARD_PROTECT_STAGES:
        return "hard_risk_gate"
    return "saved_loss_rate_high"


def _contextual_key(stage: str, family: str, session_mode: str, regime_mode: str) -> str:
    return "|".join(
        [
            str(stage or "unknown").strip().lower() or "unknown",
            str(family or "unknown").strip().lower() or "unknown",
            str(session_mode or "UNKNOWN").strip().upper() or "UNKNOWN",
            str(regime_mode or "UNKNOWN").strip().upper() or "UNKNOWN",
        ]
    )


def _recommendation_delta(*, impact_score: float, missed_win_rate: float, survival_rate: float) -> float:
    max_delta = abs(float(getattr(cfg, "OFFLINE_THRESHOLD_TUNING_MAX_DELTA", 0.03) or 0.03))
    starvation_floor = float(
        getattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", 0.25) or 0.25
    )
    survival_gap = max(0.0, starvation_floor - float(survival_rate))
    raw_delta = 0.01 + (max(0.0, min(1.0, float(impact_score))) * 0.02) + (
        max(0.0, min(1.0, float(missed_win_rate))) * 0.01
    ) + min(0.01, survival_gap * 0.05)
    return round(-_clamp(raw_delta, 0.0, max_delta), 6)


def _gate_entry(key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(payload or {})
    item["gate_key"] = str(item.get("gate_key") or key)
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


def _group_entry(key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(payload or {})
    strategy_family, direction_family, strategy_regime_mode, session_mode = (
        str(key).split("|", 3) if "|" in str(key) else ("unknown", "unknown", "UNKNOWN", "UNKNOWN")
    )
    item["group_key"] = str(key)
    item["strategy_family"] = str(item.get("strategy_family") or strategy_family).strip().lower() or "unknown"
    item["direction_family"] = str(item.get("direction_family") or direction_family).strip().lower() or "unknown"
    item["strategy_regime_mode"] = str(item.get("strategy_regime_mode") or strategy_regime_mode).strip().upper() or "UNKNOWN"
    item["session_mode"] = str(item.get("session_mode") or session_mode).strip().upper() or "UNKNOWN"
    item["raw_candidates"] = int(_safe_int(item.get("raw_candidates")) or 0)
    item["survived_candidates"] = int(_safe_int(item.get("survived_candidates")) or 0)
    item["survival_rate"] = float(_safe_float(item.get("survival_rate")) or 0.0)
    item["median_realized_r_multiple"] = _safe_float(item.get("median_realized_r_multiple"))
    item["edge_improved_flag"] = bool(item.get("edge_improved_flag", False))
    item["filtering_without_edge_flag"] = bool(item.get("filtering_without_edge_flag", False))
    return item


def _starvation_entry(group_type: str, key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(payload or {})
    item["group_type"] = str(group_type)
    item["group_key"] = str(key)
    item["strategy_family"] = str(item.get("strategy_family") or "unknown").strip().lower() or "unknown"
    item["direction_family"] = str(item.get("direction_family") or "unknown").strip().lower() or "unknown"
    item["session_mode"] = str(item.get("session_mode") or "UNKNOWN").strip().upper() or "UNKNOWN"
    item["strategy_regime_mode"] = str(item.get("strategy_regime_mode") or "UNKNOWN").strip().upper() or "UNKNOWN"
    item["raw_candidate_count"] = int(_safe_int(item.get("raw_candidate_count")) or 0)
    item["survived_candidate_count"] = int(_safe_int(item.get("survived_candidate_count")) or 0)
    item["survival_rate"] = float(_safe_float(item.get("survival_rate")) or 0.0)
    item["executable_rate"] = float(_safe_float(item.get("executable_rate")) or 0.0)
    item["advisory_rate"] = float(_safe_float(item.get("advisory_rate")) or 0.0)
    item["no_trade_rate"] = float(_safe_float(item.get("no_trade_rate")) or 0.0)
    item["top_family_share"] = float(_safe_float(item.get("top_family_share")) or 0.0)
    item["starvation_flag"] = bool(item.get("starvation_flag", False))
    item["starvation_reason"] = str(item.get("starvation_reason") or "").strip().lower() or None
    return item


def _survival_group_matches(group: Mapping[str, Any], starvation_group: Mapping[str, Any]) -> bool:
    for field in ("strategy_family", "direction_family", "session_mode", "strategy_regime_mode"):
        value = starvation_group.get(field)
        if value in (None, "", "unknown", "UNKNOWN"):
            continue
        if str(group.get(field) or "").strip() != str(value).strip():
            return False
    return True


def build_tuning_shortlist(
    *,
    rejection_impact_summary: Mapping[str, Any],
    starvation_by_group_summary: Mapping[str, Any],
    survival_expectancy_summary: Mapping[str, Any],
    top_damaging_gates: Mapping[str, Any],
    top_n: int = 3,
) -> dict[str, Any]:
    shortlist_top_n = max(
        1,
        int(top_n or getattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_TOP_N", 3) or 3),
    )
    min_missed_win_rate = float(
        getattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_MIN_MISSED_WIN_RATE", 0.30) or 0.30
    )
    min_edge_r_delta = float(
        getattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_MIN_EDGE_R_DELTA", 0.05) or 0.05
    )
    starvation_floor = float(
        getattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", 0.25) or 0.25
    )

    stage_family_map = dict((rejection_impact_summary or {}).get("by_stage_strategy_family") or {})
    all_gate_entries = [_gate_entry(key, value) for key, value in stage_family_map.items()]
    all_gate_entries.sort(
        key=lambda item: (
            -float(item.get("impact_score") or 0.0),
            -int(item.get("reject_count") or 0),
            str(item.get("gate_key") or ""),
        )
    )

    top_gate_rank_map = {
        str(item.get("gate_key") or ""): int(item.get("rank") or 0)
        for item in (top_damaging_gates or {}).get("gates", [])
        if str(item.get("gate_key") or "").strip()
    }

    protected_gate_map: dict[str, dict[str, Any]] = {}
    gates_to_protect: list[dict[str, Any]] = []
    for gate in sorted(
        all_gate_entries,
        key=lambda item: (
            -float(item.get("saved_loss_rate") or 0.0),
            float(item.get("impact_score") or 0.0),
            -int(item.get("reject_count") or 0),
            str(item.get("gate_key") or ""),
        ),
    ):
        if not should_protect_gate(gate):
            continue
        protection_reason = _protection_reason(gate)
        enriched = {
            **gate,
            "protection_reason": protection_reason,
            "gate_protected_flag": True,
            "triage_recommendation": "protect_gate",
            "top_damaging_gate_rank": top_gate_rank_map.get(str(gate.get("gate_key") or "")),
        }
        protected_gate_map[str(gate.get("gate_key") or "")] = {
            "gate_protected_flag": True,
            "protection_reason": protection_reason,
            "saved_loss_rate": round(float(gate.get("saved_loss_rate") or 0.0), 6),
        }
        gates_to_protect.append(enriched)
        if len(gates_to_protect) >= shortlist_top_n:
            break

    gates_to_loosen: list[dict[str, Any]] = []
    loosen_gate_map: dict[str, dict[str, Any]] = {}
    for gate in all_gate_entries:
        gate_key = str(gate.get("gate_key") or "")
        if gate_key in protected_gate_map:
            continue
        if float(gate.get("impact_score") or 0.0) <= 0.0:
            continue
        if float(gate.get("missed_win_rate") or 0.0) < min_missed_win_rate:
            continue
        enriched = {
            **gate,
            "gate_protected_flag": False,
            "triage_recommendation": "review_loosen_gate",
            "top_damaging_gate_rank": top_gate_rank_map.get(gate_key),
        }
        gates_to_loosen.append(enriched)
        loosen_gate_map[gate_key] = {
            "triage_recommendation": "review_loosen_gate",
            "impact_score": round(float(gate.get("impact_score") or 0.0), 6),
            "missed_win_rate": round(float(gate.get("missed_win_rate") or 0.0), 6),
            "top_damaging_gate_rank": top_gate_rank_map.get(gate_key),
        }
        if len(gates_to_loosen) >= shortlist_top_n:
            break

    survival_groups = {
        str(key): _group_entry(str(key), value)
        for key, value in dict((survival_expectancy_summary or {}).get("groups") or {}).items()
    }

    edge_improved_groups: list[dict[str, Any]] = []
    filtering_without_edge_groups: list[dict[str, Any]] = []
    edge_preserve_group_map: dict[str, dict[str, Any]] = {}
    filtering_without_edge_group_map: dict[str, dict[str, Any]] = {}
    for key, group in survival_groups.items():
        survival_rate = float(group.get("survival_rate") or 0.0)
        realized_r = _safe_float(group.get("median_realized_r_multiple"))
        edge_improved_flag = bool(
            group.get("edge_improved_flag", False)
            or (survival_rate < starvation_floor and realized_r is not None and float(realized_r) >= min_edge_r_delta)
        )
        filtering_without_edge_flag = bool(
            group.get("filtering_without_edge_flag", False)
            or (survival_rate < starvation_floor and not edge_improved_flag)
        )
        enriched = {
            **group,
            "edge_improved_flag": edge_improved_flag,
            "filtering_without_edge_flag": filtering_without_edge_flag,
        }
        if edge_improved_flag:
            enriched["triage_recommendation"] = "leave_alone_edge_improved"
            enriched["edge_preserve_flag"] = True
            edge_improved_groups.append(enriched)
            edge_preserve_group_map[key] = {
                "triage_recommendation": "leave_alone_edge_improved",
                "edge_preserve_flag": True,
            }
        if filtering_without_edge_flag:
            enriched_flag = {
                **enriched,
                "triage_recommendation": "review_filtering_without_edge",
                "edge_preserve_flag": False,
            }
            filtering_without_edge_groups.append(enriched_flag)
            filtering_without_edge_group_map[key] = {
                "triage_recommendation": "review_filtering_without_edge",
                "edge_preserve_flag": False,
            }

    edge_improved_groups.sort(
        key=lambda item: (
            float(item.get("survival_rate") or 0.0),
            -float(_safe_float(item.get("median_realized_r_multiple")) or 0.0),
            -int(item.get("raw_candidates") or 0),
            str(item.get("group_key") or ""),
        )
    )
    filtering_without_edge_groups.sort(
        key=lambda item: (
            float(item.get("survival_rate") or 0.0),
            -int(item.get("raw_candidates") or 0),
            str(item.get("group_key") or ""),
        )
    )

    starvation_groups_to_review: list[dict[str, Any]] = []
    starvation_review_group_map: dict[str, dict[str, Any]] = {}
    recommended_contextual_adjustments: dict[str, dict[str, Any]] = {}
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
            starvation_group = _starvation_entry(group_type, key, value)
            if not starvation_group.get("starvation_flag", False):
                continue
            if float(starvation_group.get("survival_rate") or 0.0) >= starvation_floor:
                continue
            matching_groups = [
                group
                for group in survival_groups.values()
                if _survival_group_matches(group, starvation_group)
            ]
            if not any(bool(group.get("filtering_without_edge_flag", False)) for group in matching_groups):
                continue
            enriched = {
                **starvation_group,
                "triage_recommendation": "review_starvation_group",
                "matching_filtering_without_edge_groups": int(
                    sum(1 for group in matching_groups if bool(group.get("filtering_without_edge_flag", False)))
                ),
            }
            starvation_groups_to_review.append(enriched)
            starvation_review_group_map[str(starvation_group.get("group_key") or "")] = {
                "triage_recommendation": "review_starvation_group",
                "group_type": str(starvation_group.get("group_type") or ""),
            }
            if group_type not in {"strategy_family__session_mode", "strategy_family__strategy_regime_mode"}:
                continue
            family = str(starvation_group.get("strategy_family") or "unknown").strip().lower() or "unknown"
            if family == "unknown":
                continue
            for group in matching_groups:
                if bool(group.get("edge_improved_flag", False)):
                    continue
                session_mode = str(group.get("session_mode") or "UNKNOWN").strip().upper() or "UNKNOWN"
                regime_mode = str(group.get("strategy_regime_mode") or "UNKNOWN").strip().upper() or "UNKNOWN"
                matching_gate = next(
                    (
                        gate
                        for gate in all_gate_entries
                        if str(gate.get("strategy_family") or "unknown").strip().lower() == family
                        and str(gate.get("rejected_at_stage") or "unknown").strip().lower() in _ADJUSTABLE_STAGES
                        and not should_protect_gate(gate)
                        and float(gate.get("impact_score") or 0.0) > 0.0
                        and float(gate.get("missed_win_rate") or 0.0) >= min_missed_win_rate
                    ),
                    None,
                )
                candidate_stage = (
                    str((matching_gate or {}).get("rejected_at_stage") or "family_survival").strip().lower()
                    or "family_survival"
                )
                if candidate_stage not in _ADJUSTABLE_STAGES:
                    candidate_stage = "family_survival"
                delta = _recommendation_delta(
                    impact_score=float((matching_gate or {}).get("impact_score") or min_missed_win_rate),
                    missed_win_rate=float((matching_gate or {}).get("missed_win_rate") or min_missed_win_rate),
                    survival_rate=float(group.get("survival_rate") or 0.0),
                )
                if delta == 0.0:
                    continue
                recommendation_key = _contextual_key(candidate_stage, family, session_mode, regime_mode)
                recommended_contextual_adjustments[recommendation_key] = {
                    "stage": candidate_stage,
                    "strategy_family": family,
                    "session_mode": session_mode,
                    "strategy_regime_mode": regime_mode,
                    "recommended_delta": delta,
                    "reason": "starvation_without_edge_improvement",
                    "confidence": round(
                        _clamp(
                            0.35
                            + min(0.35, max(0.0, float((matching_gate or {}).get("impact_score") or 0.0)) * 0.35)
                            + min(0.20, max(0.0, starvation_floor - float(group.get("survival_rate") or 0.0))),
                            0.0,
                            1.0,
                        ),
                        6,
                    ),
                    "gate_key": (matching_gate or {}).get("gate_key"),
                }

    starvation_groups_to_review.sort(
        key=lambda item: (
            float(item.get("survival_rate") or 0.0),
            -int(item.get("raw_candidate_count") or 0),
            -float(item.get("no_trade_rate") or 0.0),
            str(item.get("group_key") or ""),
        )
    )

    return {
        "top_n": int(shortlist_top_n),
        "gates_to_loosen": gates_to_loosen[:shortlist_top_n],
        "gates_to_protect": gates_to_protect[:shortlist_top_n],
        "starvation_groups_to_review": starvation_groups_to_review[:shortlist_top_n],
        "edge_improved_groups_to_leave_alone": edge_improved_groups[:shortlist_top_n],
        "filtering_without_edge_groups": filtering_without_edge_groups[:shortlist_top_n],
        "protected_gate_map": protected_gate_map,
        "loosen_gate_map": loosen_gate_map,
        "edge_preserve_group_map": edge_preserve_group_map,
        "filtering_without_edge_group_map": filtering_without_edge_group_map,
        "starvation_review_group_map": starvation_review_group_map,
        "top_damaging_gate_rank_map": top_gate_rank_map,
        "recommended_contextual_adjustments": recommended_contextual_adjustments,
    }


def rebuild_threshold_tuning_shortlist() -> dict[str, Any]:
    shortlist = build_tuning_shortlist(
        **load_threshold_triage_inputs(),
        top_n=int(getattr(cfg, "OFFLINE_THRESHOLD_TRIAGE_TOP_N", 3) or 3),
    )
    save_threshold_tuning_shortlist(shortlist)
    return shortlist

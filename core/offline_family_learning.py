from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import math
import statistics
from pathlib import Path
from typing import Any, Iterable

from config import config as cfg
from core.events import write_json_atomic
from core.log_writer import get_jsonl_writer
from core.paths import ensure_dir, runtime_dir

logger = logging.getLogger(__name__)

_STATE_CACHE: dict[str, tuple[float | None, dict[str, Any]]] = {}
_STATE_VERSION = 1


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(float(lower), min(float(upper), float(value)))


def _median(values: Iterable[float]) -> float:
    cleaned = [float(value) for value in values]
    if not cleaned:
        return 0.0
    return float(statistics.median(cleaned))


def _family_key(strategy_family: Any, direction_family: Any) -> str:
    strategy = str(strategy_family or "unknown").strip().lower() or "unknown"
    direction = str(direction_family or "unknown").strip().lower() or "unknown"
    return f"{strategy}|{direction}"


def family_learning_dir() -> Path:
    return ensure_dir(runtime_dir() / "analytics")


def family_outcome_records_path() -> Path:
    return family_learning_dir() / "family_outcomes.jsonl"


def family_learning_state_path() -> Path:
    return family_learning_dir() / "family_learning_state.json"


def _neutral_family_feedback(
    *,
    strategy_family: Any = None,
    direction_family: Any = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = None
    version = None
    if isinstance(state, dict):
        generated_at = state.get("generated_at")
        version = state.get("version")
    return {
        "strategy_family": str(strategy_family or "unknown").strip().lower() or "unknown",
        "direction_family": str(direction_family or "unknown").strip().lower() or "unknown",
        "sample_count": 0,
        "family_score_adjustment": 0.0,
        "family_signal_bias_adjustment": 0.0,
        "family_execution_bias_adjustment": 0.0,
        "family_scarcity_adjustment": 0,
        "family_confidence": 0.0,
        "family_feedback_applied": False,
        "expectancy_score": 0.0,
        "generated_at": generated_at,
        "version": version,
    }


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    strategy_family = str(record.get("strategy_family") or "unknown").strip().lower() or "unknown"
    direction_family = str(record.get("direction_family") or "unknown").strip().lower() or "unknown"
    simulation_status = str(
        record.get("simulation_status")
        or record.get("simulation_outcome")
        or record.get("status")
        or "UNKNOWN"
    ).strip().upper() or "UNKNOWN"
    normalized = {
        "timestamp": str(record.get("timestamp") or ""),
        "strategy_family": strategy_family,
        "direction_family": direction_family,
        "candidate_class": str(record.get("candidate_class") or "").strip().upper() or None,
        "selector_outcome": str(record.get("selector_outcome") or "").strip().upper() or None,
        "signal_score": _safe_float(record.get("signal_score")),
        "execution_score": _safe_float(record.get("execution_score")),
        "priority_score": _safe_float(record.get("priority_score")),
        "final_score": _safe_float(record.get("final_score")),
        "selection_probability": _safe_float(record.get("selection_probability")),
        "simulation_status": simulation_status,
        "fill_status": str(record.get("fill_status") or record.get("simulation_fill_status") or "").strip().upper() or None,
        "mfe": _safe_float(record.get("mfe")),
        "mae": _safe_float(record.get("mae")),
        "simulated_pnl": _safe_float(record.get("simulated_pnl")),
        "exit_reason": str(record.get("exit_reason") or "").strip().upper() or "UNKNOWN",
        "would_have_worked": _safe_bool(record.get("would_have_worked")),
        "rejection_saved_loss": _safe_bool(record.get("rejection_saved_loss")),
        "rejection_missed_win": _safe_bool(record.get("rejection_missed_win")),
        "realized_r_multiple": _safe_float(record.get("realized_r_multiple")),
        "stop_hit_before_target": _safe_bool(record.get("stop_hit_before_target")),
        "risk_plan_respected": _safe_bool(record.get("risk_plan_respected")),
    }
    normalized["family_key"] = _family_key(strategy_family, direction_family)
    return normalized


def summarize_family_history(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized_records = [_normalize_record(dict(record or {})) for record in (records or [])]
    pnl_scale = _median(abs(float(row["simulated_pnl"])) for row in normalized_records if row["simulated_pnl"] not in (None, 0.0))
    mfe_scale = _median(abs(float(row["mfe"])) for row in normalized_records if row["mfe"] not in (None, 0.0))
    mae_scale = _median(abs(float(row["mae"])) for row in normalized_records if row["mae"] not in (None, 0.0))
    r_multiple_scale = _median(
        abs(float(row["realized_r_multiple"]))
        for row in normalized_records
        if row["realized_r_multiple"] not in (None, 0.0)
    )
    pnl_scale = pnl_scale or 1.0
    mfe_scale = mfe_scale or pnl_scale or 1.0
    mae_scale = mae_scale or pnl_scale or 1.0
    r_multiple_scale = r_multiple_scale or 1.0

    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in normalized_records:
        buckets.setdefault(row["family_key"], []).append(row)

    summaries: dict[str, dict[str, Any]] = {}
    for key, bucket in buckets.items():
        sample_count = len(bucket)
        pnls = [float(row["simulated_pnl"]) for row in bucket if row["simulated_pnl"] is not None]
        mfes = [float(row["mfe"]) for row in bucket if row["mfe"] is not None]
        maes = [float(row["mae"]) for row in bucket if row["mae"] is not None]
        realized_rs = [float(row["realized_r_multiple"]) for row in bucket if row["realized_r_multiple"] is not None]
        win_rate = sum(
            1
            for row in bucket
            if (row["simulated_pnl"] is not None and float(row["simulated_pnl"]) > 0.0) or bool(row["would_have_worked"])
        ) / max(1, sample_count)
        would_have_worked_rate = sum(1 for row in bucket if bool(row["would_have_worked"])) / max(1, sample_count)
        rejection_saved_loss_rate = sum(1 for row in bucket if bool(row["rejection_saved_loss"])) / max(1, sample_count)
        rejection_missed_win_rate = sum(1 for row in bucket if bool(row["rejection_missed_win"])) / max(1, sample_count)
        opportunity_conversion_rate = sum(
            1 for row in bucket if str(row.get("simulation_status") or "").strip().upper() in {"SIM_EXECUTED", "SIM_PARTIAL_FILL"}
        ) / max(1, sample_count)
        risk_plan_respected_rate = sum(1 for row in bucket if bool(row["risk_plan_respected"])) / max(1, sample_count)
        stop_hit_before_target_rate = sum(1 for row in bucket if bool(row["stop_hit_before_target"])) / max(1, sample_count)

        median_pnl = _median(pnls)
        median_mfe = _median(mfes)
        median_mae = _median(maes)
        median_realized_r_multiple = _median(realized_rs)
        pnl_component = math.tanh(median_pnl / max(pnl_scale, 1e-6))
        win_proxy = ((win_rate * 0.6) + (would_have_worked_rate * 0.4) - 0.5) * 2.0
        win_component = _clamp(win_proxy, -1.0, 1.0)
        mfe_component = math.tanh(median_mfe / max(mfe_scale, 1e-6))
        mae_component = -math.tanh(abs(min(median_mae, 0.0)) / max(mae_scale, 1e-6))
        realized_r_component = math.tanh(median_realized_r_multiple / max(r_multiple_scale, 1e-6))
        saved_loss_component = -float(rejection_saved_loss_rate)
        missed_win_component = float(rejection_missed_win_rate)
        weights = [
            float(getattr(cfg, "OFFLINE_FAMILY_LEARNING_EXPECTANCY_WEIGHT", 0.36)),
            float(getattr(cfg, "OFFLINE_FAMILY_LEARNING_WIN_RATE_WEIGHT", 0.24)),
            float(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MFE_WEIGHT", 0.12)),
            float(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MAE_WEIGHT", 0.12)),
            float(getattr(cfg, "OFFLINE_FAMILY_LEARNING_REJECTION_SAVED_LOSS_WEIGHT", 0.10)),
            float(getattr(cfg, "OFFLINE_FAMILY_LEARNING_REJECTION_MISSED_WIN_WEIGHT", 0.06)),
        ]
        weighted_sum = (
            (pnl_component * weights[0])
            + (win_component * weights[1])
            + (mfe_component * weights[2])
            + (mae_component * weights[3])
            + (saved_loss_component * weights[4])
            + (missed_win_component * weights[5])
            + (realized_r_component * 0.08)
        )
        expectancy_score = weighted_sum / max(sum(weights) + 0.08, 1e-6)
        strategy_family, direction_family = key.split("|", 1)
        summaries[key] = {
            "strategy_family": strategy_family,
            "direction_family": direction_family,
            "sample_count": int(sample_count),
            "win_rate": round(float(win_rate), 6),
            "median_pnl": round(float(median_pnl), 6),
            "median_mfe": round(float(median_mfe), 6),
            "median_mae": round(float(median_mae), 6),
            "would_have_worked_rate": round(float(would_have_worked_rate), 6),
            "rejection_saved_loss_rate": round(float(rejection_saved_loss_rate), 6),
            "rejection_missed_win_rate": round(float(rejection_missed_win_rate), 6),
            "opportunity_conversion_rate": round(float(opportunity_conversion_rate), 6),
            "risk_plan_respected_rate": round(float(risk_plan_respected_rate), 6),
            "stop_hit_before_target_rate": round(float(stop_hit_before_target_rate), 6),
            "median_realized_r_multiple": round(float(median_realized_r_multiple), 6),
            "expectancy_score": round(float(_clamp(expectancy_score, -1.0, 1.0)), 6),
        }
    return summaries


def derive_family_feedback(summary: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    min_samples = max(1, int(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MIN_SAMPLES", 25) or 25))
    max_adjustment = max(0.0, float(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MAX_ADJUSTMENT", 0.06) or 0.06))
    max_scarcity_delta = max(0, int(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MAX_SCARCITY_DELTA", 1) or 1))
    feedback: dict[str, dict[str, Any]] = {}
    for key, row in (summary or {}).items():
        sample_count = int(row.get("sample_count") or 0)
        expectancy_score = float(row.get("expectancy_score") or 0.0)
        if sample_count < min_samples:
            feedback[key] = {
                **row,
                "family_score_adjustment": 0.0,
                "family_signal_bias_adjustment": 0.0,
                "family_execution_bias_adjustment": 0.0,
                "family_scarcity_adjustment": 0,
                "family_confidence": 0.0,
                "family_feedback_applied": False,
            }
            continue
        shrinkage = float(sample_count) / float(sample_count + (min_samples * 2))
        conversion = float(row.get("opportunity_conversion_rate") or 0.0)
        family_confidence = _clamp(shrinkage * (0.5 + (0.5 * conversion)), 0.0, 1.0)
        score_adjustment = _clamp(expectancy_score * max_adjustment * shrinkage, -max_adjustment, max_adjustment)
        signal_bias_adjustment = _clamp(score_adjustment * 0.5, -(max_adjustment * 0.5), max_adjustment * 0.5)
        execution_bias_adjustment = _clamp(
            (
                (float(row.get("rejection_saved_loss_rate") or 0.0) - float(row.get("rejection_missed_win_rate") or 0.0))
                * max_adjustment
                * shrinkage
            ),
            -(max_adjustment * 0.5),
            max_adjustment * 0.5,
        )
        scarcity_adjustment = 0
        scarcity_trigger = max_adjustment * 0.5
        if family_confidence >= 0.45 and score_adjustment >= scarcity_trigger:
            scarcity_adjustment = min(max_scarcity_delta, 1)
        elif family_confidence >= 0.45 and score_adjustment <= -scarcity_trigger:
            scarcity_adjustment = max(-max_scarcity_delta, -1)
        feedback[key] = {
            **row,
            "family_score_adjustment": round(float(score_adjustment), 6),
            "family_signal_bias_adjustment": round(float(signal_bias_adjustment), 6),
            "family_execution_bias_adjustment": round(float(execution_bias_adjustment), 6),
            "family_scarcity_adjustment": int(scarcity_adjustment),
            "family_confidence": round(float(family_confidence), 6),
            "family_feedback_applied": bool(
                abs(float(score_adjustment)) >= 0.005 or scarcity_adjustment != 0
            ),
        }
    return feedback


def save_family_learning_state(state: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path is not None else family_learning_state_path()
    write_json_atomic(target, state)
    try:
        mtime = target.stat().st_mtime if target.exists() else None
    except Exception:
        mtime = None
    _STATE_CACHE[str(target)] = (mtime, dict(state or {}))
    return target


def load_family_learning_state(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else family_learning_state_path()
    if not target.exists():
        return {
            "version": _STATE_VERSION,
            "generated_at": None,
            "min_samples": int(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MIN_SAMPLES", 25) or 25),
            "families": {},
        }
    try:
        mtime = target.stat().st_mtime
    except Exception:
        mtime = None
    cache_key = str(target)
    cached = _STATE_CACHE.get(cache_key)
    if cached is not None and cached[0] == mtime:
        return dict(cached[1])
    try:
        state = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("offline_family_learning_state_load_failed path=%s", target)
        return {
            "version": _STATE_VERSION,
            "generated_at": None,
            "min_samples": int(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MIN_SAMPLES", 25) or 25),
            "families": {},
        }
    _STATE_CACHE[cache_key] = (mtime, dict(state or {}))
    return dict(state or {})


def load_family_outcome_records(path: str | Path | None = None) -> list[dict[str, Any]]:
    target = Path(path).expanduser() if path is not None else family_outcome_records_path()
    if not target.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def rebuild_family_learning_state(
    *,
    records: Iterable[dict[str, Any]] | None = None,
    records_path: str | Path | None = None,
    state_path: str | Path | None = None,
) -> dict[str, Any]:
    raw_records = list(records) if records is not None else load_family_outcome_records(records_path)
    summary = summarize_family_history(raw_records)
    feedback = derive_family_feedback(summary)
    families: dict[str, dict[str, Any]] = {}
    for key, row in summary.items():
        families[key] = {
            **row,
            **feedback.get(key, {}),
        }
    state = {
        "version": _STATE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_samples": int(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MIN_SAMPLES", 25) or 25),
        "families": families,
    }
    save_family_learning_state(state, path=state_path)
    if bool(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_LEARNING_ENABLE", False)):
        try:
            from core.strategy_weight_learning import rebuild_strategy_weight_state

            rebuild_strategy_weight_state(family_learning_state=state)
        except Exception:
            logger.warning("offline_strategy_weight_state_update_failed", exc_info=True)
    logger.info(
        "OFFLINE_FAMILY_LEARNING_STATE_UPDATED %s",
        {
            "family_count": len(families),
            "record_count": len(raw_records),
            "state_path": str(Path(state_path).expanduser() if state_path is not None else family_learning_state_path()),
        },
    )
    return state


def append_family_outcome_record(record: dict[str, Any], path: str | Path | None = None) -> dict[str, Any]:
    normalized = json.loads(json.dumps(dict(record or {}), sort_keys=True, ensure_ascii=True, default=str))
    target = Path(path).expanduser() if path is not None else family_outcome_records_path()
    writer = get_jsonl_writer(target)
    writer.write(normalized)
    return normalized


def record_family_outcome(
    record: dict[str, Any],
    *,
    records_path: str | Path | None = None,
    state_path: str | Path | None = None,
) -> dict[str, Any]:
    normalized = append_family_outcome_record(record, path=records_path)
    state = rebuild_family_learning_state(records_path=records_path, state_path=state_path)
    logger.info(
        "OFFLINE_FAMILY_OUTCOME_RECORDED %s",
        {
            "strategy_family": normalized.get("strategy_family"),
            "direction_family": normalized.get("direction_family"),
            "simulation_status": normalized.get("simulation_status"),
            "state_generated_at": state.get("generated_at"),
        },
    )
    return normalized


def lookup_family_feedback(
    strategy_family: Any,
    direction_family: Any,
    *,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    learning_state = dict(state or load_family_learning_state())
    key = _family_key(strategy_family, direction_family)
    family_row = ((learning_state.get("families") or {}) or {}).get(key)
    if not isinstance(family_row, dict):
        return _neutral_family_feedback(
            strategy_family=strategy_family,
            direction_family=direction_family,
            state=learning_state,
        )
    return {
        **_neutral_family_feedback(
            strategy_family=strategy_family,
            direction_family=direction_family,
            state=learning_state,
        ),
        **family_row,
    }

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import math
import statistics
from pathlib import Path
from typing import Any

from config import config as cfg
from core.events import write_json_atomic
from core.paths import runtime_dir

logger = logging.getLogger(__name__)

_STATE_VERSION = 1
_STATE_CACHE: dict[str, tuple[float | None, dict[str, Any]]] = {}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(float(lower), min(float(upper), float(value)))


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(statistics.median([float(value) for value in values]))


def _strategy_key(strategy_family: Any, direction_family: Any) -> str:
    strategy = str(strategy_family or "unknown").strip().lower() or "unknown"
    direction = str(direction_family or "unknown").strip().lower() or "unknown"
    return f"{strategy}|{direction}"


def strategy_weight_state_path() -> Path:
    return runtime_dir() / "analytics" / "strategy_weight_state.json"


def _neutral_strategy_weight(
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
        "samples": 0,
        "strategy_weight_adjustment": 0.0,
        "strategy_weight_confidence": 0.0,
        "strategy_execution_bias_adjustment": 0.0,
        "strategy_signal_bias_adjustment": 0.0,
        "strategy_scarcity_adjustment": 0,
        "strategy_weight_applied": False,
        "weight_adj": 0.0,
        "confidence": 0.0,
        "generated_at": generated_at,
        "version": version,
    }


def save_strategy_weight_state(state: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path is not None else strategy_weight_state_path()
    write_json_atomic(target, state)
    try:
        mtime = target.stat().st_mtime if target.exists() else None
    except Exception:
        mtime = None
    _STATE_CACHE[str(target)] = (mtime, dict(state or {}))
    return target


def load_strategy_weight_state(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path is not None else strategy_weight_state_path()
    if not target.exists():
        return {
            "version": _STATE_VERSION,
            "generated_at": None,
            "min_samples": int(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MIN_SAMPLES", 40) or 40),
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
        logger.warning("strategy_weight_state_load_failed path=%s", target)
        return {
            "version": _STATE_VERSION,
            "generated_at": None,
            "min_samples": int(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MIN_SAMPLES", 40) or 40),
            "families": {},
        }
    _STATE_CACHE[cache_key] = (mtime, dict(state or {}))
    return dict(state or {})


def update_strategy_weights_from_outcomes(
    family_learning_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    learning_state = dict(family_learning_state or {})
    family_rows = dict((learning_state.get("families") or {}) or {})
    min_samples = max(1, int(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MIN_SAMPLES", 40) or 40))
    max_adjustment = max(0.0, float(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MAX_ADJUSTMENT", 0.04) or 0.04))
    max_signal_bias = max(0.0, float(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MAX_SIGNAL_BIAS", 0.015) or 0.015))
    max_execution_bias = max(0.0, float(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MAX_EXECUTION_BIAS", 0.015) or 0.015))
    max_scarcity_delta = max(0, int(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MAX_SCARCITY_DELTA", 1) or 1))

    pnl_scale = _median(
        [abs(float(row.get("median_pnl") or 0.0)) for row in family_rows.values() if _safe_float(row.get("median_pnl")) not in (None, 0.0)]
    ) or 1.0
    mfe_scale = _median(
        [abs(float(row.get("median_mfe") or 0.0)) for row in family_rows.values() if _safe_float(row.get("median_mfe")) not in (None, 0.0)]
    ) or 1.0
    mae_scale = _median(
        [abs(float(row.get("median_mae") or 0.0)) for row in family_rows.values() if _safe_float(row.get("median_mae")) not in (None, 0.0)]
    ) or 1.0

    families: dict[str, dict[str, Any]] = {}
    for key, row in family_rows.items():
        strategy_family = str(row.get("strategy_family") or "").strip().lower() or "unknown"
        direction_family = str(row.get("direction_family") or "").strip().lower() or "unknown"
        sample_count = int(row.get("sample_count") or 0)
        expectancy_score = float(row.get("expectancy_score") or 0.0)
        if sample_count < min_samples:
            families[key] = {
                **row,
                **_neutral_strategy_weight(
                    strategy_family=strategy_family,
                    direction_family=direction_family,
                    state=learning_state,
                ),
                "sample_count": sample_count,
                "samples": sample_count,
            }
            continue
        shrinkage = float(sample_count) / float(sample_count + (min_samples * 2))
        family_confidence = _clamp(float(row.get("family_confidence") or 0.0) * shrinkage, 0.0, 1.0)
        win_component = _clamp(((float(row.get("win_rate") or 0.0) - 0.5) * 2.0), -1.0, 1.0)
        pnl_component = math.tanh(float(row.get("median_pnl") or 0.0) / max(pnl_scale, 1e-6))
        mfe_component = math.tanh(float(row.get("median_mfe") or 0.0) / max(mfe_scale, 1e-6))
        mae_component = -math.tanh(abs(min(float(row.get("median_mae") or 0.0), 0.0)) / max(mae_scale, 1e-6))
        combined = (
            expectancy_score * float(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_EXPECTANCY_WEIGHT", 0.36))
            + win_component * float(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_WIN_RATE_WEIGHT", 0.22))
            + pnl_component * float(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_PNL_WEIGHT", 0.14))
            + mfe_component * float(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MFE_WEIGHT", 0.14))
            + mae_component * float(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MAE_WEIGHT", 0.14))
        )
        strategy_weight_adjustment = _clamp(
            combined * max_adjustment * family_confidence,
            -max_adjustment,
            max_adjustment,
        )
        strategy_signal_bias_adjustment = _clamp(
            expectancy_score * max_signal_bias * family_confidence,
            -max_signal_bias,
            max_signal_bias,
        )
        strategy_execution_bias_adjustment = _clamp(
            (
                (float(row.get("rejection_saved_loss_rate") or 0.0) - float(row.get("rejection_missed_win_rate") or 0.0))
                * max_execution_bias
                * family_confidence
            ),
            -max_execution_bias,
            max_execution_bias,
        )
        strategy_scarcity_adjustment = 0
        if family_confidence >= 0.45 and strategy_weight_adjustment >= (max_adjustment * 0.5):
            strategy_scarcity_adjustment = min(max_scarcity_delta, 1)
        elif family_confidence >= 0.45 and strategy_weight_adjustment <= -(max_adjustment * 0.5):
            strategy_scarcity_adjustment = max(-max_scarcity_delta, -1)
        families[key] = {
            **row,
            "strategy_family": strategy_family,
            "direction_family": direction_family,
            "strategy_weight_adjustment": round(float(strategy_weight_adjustment), 6),
            "strategy_weight_confidence": round(float(family_confidence), 6),
            "strategy_execution_bias_adjustment": round(float(strategy_execution_bias_adjustment), 6),
            "strategy_signal_bias_adjustment": round(float(strategy_signal_bias_adjustment), 6),
            "strategy_scarcity_adjustment": int(strategy_scarcity_adjustment),
            "strategy_weight_applied": bool(
                abs(float(strategy_weight_adjustment)) >= 0.004 or strategy_scarcity_adjustment != 0
            ),
            "weight_adj": round(float(strategy_weight_adjustment), 6),
            "confidence": round(float(family_confidence), 6),
            "samples": sample_count,
        }
    return {
        "version": _STATE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_samples": min_samples,
        "families": families,
    }


def rebuild_strategy_weight_state(
    *,
    family_learning_state: dict[str, Any] | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    state = update_strategy_weights_from_outcomes(family_learning_state)
    save_strategy_weight_state(state, path=path)
    logger.info(
        "OFFLINE_STRATEGY_WEIGHT_STATE_UPDATED %s",
        {
            "family_count": len((state.get("families") or {}) or {}),
            "state_path": str(Path(path).expanduser() if path is not None else strategy_weight_state_path()),
        },
    )
    return state


def lookup_strategy_weight(
    strategy_family: Any,
    direction_family: Any,
    *,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    weight_state = dict(state or load_strategy_weight_state())
    key = _strategy_key(strategy_family, direction_family)
    row = ((weight_state.get("families") or {}) or {}).get(key)
    if not isinstance(row, dict):
        return _neutral_strategy_weight(
            strategy_family=strategy_family,
            direction_family=direction_family,
            state=weight_state,
        )
    return {
        **_neutral_strategy_weight(
            strategy_family=strategy_family,
            direction_family=direction_family,
            state=weight_state,
        ),
        **row,
    }

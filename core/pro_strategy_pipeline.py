from __future__ import annotations

import logging
from typing import Any

from config import config as cfg
from config.config import pro_strategy_flags_snapshot
from strategies.pro_layer.pro_decision_adapter import evaluate_pro_strategy_candidates


logger = logging.getLogger(__name__)


def _flags_enabled() -> dict[str, bool]:
    return dict(pro_strategy_flags_snapshot())


def _any_enabled(flags: dict[str, bool]) -> bool:
    # Shadow mode is the only activation path for now; the live layer flag is reserved.
    return bool(flags.get("ENABLE_PRO_STRATEGY_SHADOW", False))


def run_pro_strategy_pipeline(
    market_data_list: list[dict[str, Any]] | None,
    *,
    now_ts: float | None = None,
) -> dict[str, Any]:
    flags = _flags_enabled()
    if not _any_enabled(flags):
        return {"enabled": False, "flags": flags, "candidates": [], "errors": []}

    market_data_list = list(market_data_list or [])
    result: dict[str, Any] = {
        "enabled": True,
        "flags": flags,
        "candidates": [],
        "errors": [],
    }

    candidates: list[dict[str, Any]] = []
    pipeline_errors: list[str] = []
    for market_data in market_data_list:
        try:
            decisions = evaluate_pro_strategy_candidates(market_data, error_sink=pipeline_errors)
            decision = decisions[0] if decisions else None
            if decision:
                candidates.append(decision)
        except Exception as exc:
            logger.exception("pro_strategy_pipeline_item_failed err=%s", exc)
            symbol = "unknown"
            if isinstance(market_data, dict):
                symbol = market_data.get("symbol") or "unknown"
            result["errors"].append(f"pro_strategy_failed:{type(exc).__name__}:symbol={symbol}:{exc}")

    result["candidates"] = candidates
    result["errors"].extend(pipeline_errors)
    logger.info(
        "pro_strategy_pipeline_summary enabled=%s candidates=%s errors=%s strict_mode=%s live_layer=%s",
        result["enabled"],
        len(result.get("candidates") or []),
        len(result.get("errors") or []),
        bool(getattr(cfg, "PRO_STRATEGY_LAYER_STRICT_MODE", True)),
        bool(getattr(cfg, "ENABLE_PRO_STRATEGY_LAYER", False)),
    )
    return result

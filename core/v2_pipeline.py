from __future__ import annotations

import logging
from typing import Any

from config import config as cfg
from core.candidate_generator import generate_candidates
from core.stock_option_rules import stock_option_v2_enabled


logger = logging.getLogger(__name__)


def _flags_enabled() -> dict[str, bool]:
    return {
        "ENABLE_CANDIDATE_GENERATOR_V2": bool(getattr(cfg, "ENABLE_CANDIDATE_GENERATOR_V2", False)),
        "ENABLE_STOCK_OPTION_CANDIDATE_GENERATOR_V2": bool(stock_option_v2_enabled()),
    }


def _any_enabled(flags: dict[str, bool]) -> bool:
    return any(bool(value) for value in flags.values())


def run_v2_pipeline(
    market_data_list: list[dict[str, Any]] | None,
    *,
    now_ts: float | None = None,
) -> dict[str, Any]:
    flags = _flags_enabled()
    if not _any_enabled(flags):
        return {"enabled": False, "flags": flags, "candidates": []}

    market_data_list = list(market_data_list or [])
    market_data_by_symbol = {
        row.get("symbol"): row for row in market_data_list if isinstance(row, dict) and row.get("symbol")
    }

    result: dict[str, Any] = {
        "enabled": True,
        "flags": flags,
        "candidates": [],
        "errors": [],
    }

    candidates: list[dict[str, Any]] = []
    try:
        if flags.get("ENABLE_CANDIDATE_GENERATOR_V2") or flags.get("ENABLE_STOCK_OPTION_CANDIDATE_GENERATOR_V2"):
            candidates = generate_candidates(market_data_by_symbol, ts_epoch=now_ts)
        result["candidates"] = candidates
    except Exception as exc:
        logger.exception("v2_candidate_generator_failed err=%s", exc)
        result["errors"].append(f"candidate_generator_failed:{type(exc).__name__}")

    logger.info(
        "v2_pipeline_summary enabled=%s stock_options=%s candidates=%s errors=%s",
        result["enabled"],
        flags.get("ENABLE_STOCK_OPTION_CANDIDATE_GENERATOR_V2", False),
        len(result.get("candidates") or []),
        len(result.get("errors") or []),
    )
    return result

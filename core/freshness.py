from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config import config as cfg
from core.events import write_json_atomic
from core.freshness_evaluator import FreshnessDecision, evaluate_quote_freshness as _evaluate_quote_freshness, freshness_public_fields
from core.paths import logs_dir
from core.log_writer import get_jsonl_writer

logger = logging.getLogger(__name__)
_MIN_PERSIST_EPOCH = 1577836800.0


def freshness_latest_path() -> Path:
    return logs_dir() / "freshness_latest.json"


def freshness_decisions_path() -> Path:
    return logs_dir() / "freshness_decisions.jsonl"


def _latest_payload() -> dict[str, Any]:
    path = freshness_latest_path()
    if not path.exists():
        return {"updated_at": None, "decisions": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"updated_at": None, "decisions": {}}
    if not isinstance(payload, dict):
        return {"updated_at": None, "decisions": {}}
    decisions = payload.get("decisions")
    if not isinstance(decisions, dict):
        payload["decisions"] = {}
    return payload


def _update_freshness_latest(decision: FreshnessDecision) -> None:
    path = freshness_latest_path()
    payload = _latest_payload()
    decisions = payload.setdefault("decisions", {})
    symbol_key = str(decision.symbol or "UNKNOWN").upper()
    symbol_block = decisions.get(symbol_key)
    if not isinstance(symbol_block, dict):
        symbol_block = {}
    symbol_block[str(decision.decision_type)] = decision.to_dict()
    decisions[symbol_key] = symbol_block
    payload["updated_at"] = decision.ts_iso
    write_json_atomic(path, payload)


def _append_freshness_history(decision: FreshnessDecision) -> None:
    path = freshness_decisions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    get_jsonl_writer(path).write(decision.to_dict())


def record_freshness_decision(decision: FreshnessDecision) -> None:
    if float(decision.now_epoch) < _MIN_PERSIST_EPOCH:
        logger.warning(
            "freshness_decision_persist_skipped_invalid_epoch symbol=%s decision_type=%s trade_id=%s now_epoch=%s",
            decision.symbol,
            decision.decision_type,
            decision.trade_id,
            decision.now_epoch,
        )
        return
    try:
        _update_freshness_latest(decision)
        _append_freshness_history(decision)
    except Exception as exc:
        logger.warning("freshness_decision_log_failed symbol=%s decision_type=%s error=%s", decision.symbol, decision.decision_type, exc)


def evaluate_quote_freshness(
    *,
    symbol: str,
    instrument_token: Any,
    quote_epoch: Any,
    candle_epoch: Any,
    threshold_sec: Any,
    market_open: bool,
    trade_id: str | None = None,
    allow_candle_fallback: bool = False,
    decision_type: str = "option_quote",
    now_epoch: float | None = None,
    persist_runtime: bool = False,
) -> FreshnessDecision:
    decision = _evaluate_quote_freshness(
        symbol=symbol,
        instrument_token=instrument_token,
        quote_epoch=quote_epoch,
        candle_epoch=candle_epoch,
        threshold_sec=threshold_sec,
        market_open=market_open,
        trade_id=trade_id,
        allow_candle_fallback=allow_candle_fallback,
        decision_type=decision_type,
        now_epoch=now_epoch,
    )
    if bool(persist_runtime):
        record_freshness_decision(decision)
    return decision

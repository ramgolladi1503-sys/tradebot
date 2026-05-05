from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from strategies.pro_layer.pro_strategy_engine import ProSignal

DEFAULT_SHADOW_LOG_PATH = Path("logs/pro_alpha_shadow.jsonl")


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_shadow_record(
    *,
    signal: ProSignal,
    market_data: dict[str, Any],
    decision: dict[str, Any] | None = None,
    ts_epoch: float | None = None,
) -> dict[str, Any]:
    now = float(ts_epoch if ts_epoch is not None else time.time())
    source_flags = market_data.get("source_flags") or {}
    return {
        "ts_epoch": now,
        "symbol": market_data.get("symbol"),
        "instrument_id": market_data.get("instrument_id"),
        "strategy": signal.name,
        "strategy_family": signal.family,
        "direction": signal.direction,
        "score": signal.score,
        "confidence": signal.confidence,
        "reason": signal.reason,
        "regime": market_data.get("regime"),
        "entry_price": market_data.get("execution_entry") or market_data.get("entry_price") or market_data.get("ltp"),
        "stop_loss": market_data.get("stop_loss"),
        "target": market_data.get("target"),
        "ltp": market_data.get("ltp"),
        "quote_age_sec": market_data.get("quote_age_sec"),
        "spread_pct": market_data.get("spread_pct"),
        "best_bid": market_data.get("best_bid"),
        "best_ask": market_data.get("best_ask"),
        "volume": market_data.get("volume"),
        "atr": market_data.get("atr"),
        "vol_z": market_data.get("vol_z"),
        "vwap": market_data.get("vwap"),
        "bid_qty": market_data.get("bid_qty"),
        "ask_qty": market_data.get("ask_qty"),
        "iv_change": market_data.get("iv_change"),
        "call_oi_delta": market_data.get("call_oi_delta"),
        "put_oi_delta": market_data.get("put_oi_delta"),
        "decision_action": None if decision is None else decision.get("decision_action"),
        "decision_reason": None if decision is None else decision.get("decision_reason"),
        "final_score": None if decision is None else decision.get("final_score"),
        "execution_status": None if decision is None else decision.get("execution_status"),
        "source_flags": source_flags,
        "evidence": signal.evidence,
        "outcome_status": "UNLABELED",
    }


def append_shadow_record(record: dict[str, Any], *, path: Path | str = DEFAULT_SHADOW_LOG_PATH) -> None:
    out_path = Path(path)
    _ensure_parent(out_path)
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def log_shadow_signal(
    *,
    signal: ProSignal,
    market_data: dict[str, Any],
    decision: dict[str, Any] | None = None,
    path: Path | str = DEFAULT_SHADOW_LOG_PATH,
) -> dict[str, Any]:
    record = build_shadow_record(signal=signal, market_data=market_data, decision=decision)
    append_shadow_record(record, path=path)
    return record


def load_shadow_records(*, path: Path | str = DEFAULT_SHADOW_LOG_PATH) -> list[dict[str, Any]]:
    in_path = Path(path)
    if not in_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in in_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except Exception:
            continue
    return rows

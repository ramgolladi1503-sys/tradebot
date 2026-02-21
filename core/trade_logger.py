# Migration note:
# Trade logger now resolves canonical trade-log path through core.trade_log_paths.

import json
from datetime import datetime
from core.trade_store import (
    insert_trade,
    insert_outcome,
    update_trade_fill_db,
    update_trade_close,
    classify_outcome_label,
    classify_outcome_grade,
)
from config import config as cfg
from core import log_lock
from pathlib import Path
from core.trade_schema import build_instrument_id, validate_trade_identity
from core.post_trade_labeler import PostTradeLabeler
from core.trade_log_paths import ensure_trade_log_file
import time


_POST_TRADE_LABELER = PostTradeLabeler()


def _trade_log_path() -> Path:
    return ensure_trade_log_file(create_if_missing=True)


def _safe_emit_post_trade_label(entry: dict) -> None:
    try:
        _POST_TRADE_LABELER.label_and_persist(
            entry,
            decision_trace_id=entry.get("decision_trace_id") or entry.get("trade_id"),
            features_snapshot=entry.get("features_snapshot"),
            regime_at_entry=entry.get("regime"),
        )
    except Exception as exc:
        _log_error(
            {
                "error": "post_trade_label_failed",
                "trade_id": entry.get("trade_id"),
                "detail": str(exc),
            }
        )


def log_trade(trade, extra=None):
    instrument_type = getattr(trade, "instrument_type", None) or getattr(trade, "instrument", None)
    right = getattr(trade, "right", None) or getattr(trade, "option_type", None)
    underlying = getattr(trade, "symbol", None)
    expiry = getattr(trade, "expiry", None)
    strike = getattr(trade, "strike", None)
    ok, reason = validate_trade_identity(underlying, instrument_type, expiry, strike, right)
    instrument_id = build_instrument_id(underlying, instrument_type, expiry, strike, right)
    if not ok or not instrument_id:
        _log_error({
            "error": "missing_contract_fields",
            "reason": reason,
            "trade_id": getattr(trade, "trade_id", None),
            "symbol": underlying,
            "instrument_type": instrument_type,
            "expiry": expiry,
            "strike": strike,
            "right": right,
        })
        return
    lot_size = int(getattr(cfg, "LOT_SIZE", {}).get(underlying, 1))
    qty_lots = int(getattr(trade, "qty", 0) or 0)
    qty_units = qty_lots * (lot_size if instrument_type == "OPT" else 1)
    log_entry = {
        "trade_id": trade.trade_id,
        "trace_id": trade.trade_id,
        "decision_trace_id": trade.trade_id,
        "timestamp": str(datetime.now()),
        "symbol": trade.symbol,
        "underlying": underlying,
        "instrument": trade.instrument,
        "instrument_type": instrument_type,
        "instrument_token": trade.instrument_token,
        "strike": getattr(trade, "strike", None),
        "expiry": getattr(trade, "expiry", None),
        "option_type": getattr(trade, "option_type", None),
        "right": right,
        "instrument_id": instrument_id,
        "side": trade.side,
        "entry": trade.entry_price,
        "target": trade.target,
        "qty": trade.qty,
        "qty_lots": qty_lots,
        "qty_units": qty_units,
        "validity_sec": getattr(trade, "validity_sec", None),
        "tradable": bool(getattr(trade, "tradable", True)),
        "tradable_reasons_blocking": json.dumps(list(getattr(trade, "tradable_reasons_blocking", []) or [])),
        "source_flags_json": json.dumps(dict(getattr(trade, "source_flags", {}) or {})),
        "confidence": trade.confidence,
        "stop_loss": trade.stop_loss,
        "capital_at_risk": trade.capital_at_risk,
        "regime": trade.regime,
        "strategy": trade.strategy,
        "tier": getattr(trade, "tier", "MAIN"),
        "day_type": getattr(trade, "day_type", "UNKNOWN"),
        "features_snapshot": {
            "trade_score": getattr(trade, "trade_score", None),
            "trade_score_detail": getattr(trade, "trade_score_detail", None),
            "opt_ltp": getattr(trade, "opt_ltp", None),
            "opt_bid": getattr(trade, "opt_bid", None),
            "opt_ask": getattr(trade, "opt_ask", None),
            "model_type": getattr(trade, "model_type", None),
            "model_version": getattr(trade, "model_version", None),
            "alpha_confidence": getattr(trade, "alpha_confidence", None),
            "alpha_uncertainty": getattr(trade, "alpha_uncertainty", None),
        },
        "predicted": 1 if trade.side == "BUY" else 0,
        "actual": None,
        "exit_price": None,
        "exit_time": None
    }
    if extra:
        log_entry.update(extra)

    trade_log_path = _trade_log_path()
    with trade_log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
    try:
        insert_trade(log_entry)
    except Exception as exc:
        _log_error({"error": "insert_trade_failed", "detail": str(exc), "trade_id": trade.trade_id})

def _append_update(update_entry):
    with open("data/trade_updates.json", "a") as f:
        f.write(json.dumps(update_entry) + "\n")


def _log_error(payload: dict) -> None:
    try:
        path = Path("logs/trade_logger_errors.jsonl")
        path.parent.mkdir(exist_ok=True)
        payload = dict(payload)
        payload.setdefault("ts", time.time())
        with path.open("a") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        print("[TRADE_LOGGER_ERROR] failed to write error log")


def _compute_realized_metrics(entry: dict, exit_price: float, actual: int, exit_reason: str | None = None) -> dict:
    side = entry.get("side", "BUY")
    entry_price = float(entry.get("entry", 0) or 0)
    stop = float(entry.get("stop_loss", 0) or 0)
    qty_units = entry.get("qty_units")
    if qty_units is None:
        qty = int(entry.get("qty", 0) or 0)
        lot_size = int(getattr(cfg, "LOT_SIZE", {}).get(entry.get("symbol"), 1))
        instrument = entry.get("instrument")
        qty_units = qty * (lot_size if instrument == "OPT" else 1)
    qty_units = int(qty_units or 0)
    if side == "BUY":
        realized_pnl = (float(exit_price) - entry_price) * qty_units
    else:
        realized_pnl = (entry_price - float(exit_price)) * qty_units
    per_unit_risk = abs(entry_price - stop)
    total_risk = per_unit_risk * qty_units
    if total_risk > 0:
        r_multiple_realized = realized_pnl / total_risk
    else:
        r_multiple_realized = 0.0
    epsilon = float(getattr(cfg, "OUTCOME_PNL_EPSILON", 1e-6))
    outcome_label = classify_outcome_label(realized_pnl, epsilon=epsilon)
    outcome_grade = classify_outcome_grade(r_multiple_realized)
    derived_exit_reason = exit_reason
    if not derived_exit_reason:
        derived_exit_reason = "TARGET" if actual == 1 else "STOP"
    return {
        "entry_price": entry_price,
        "qty_units": qty_units,
        "realized_pnl": round(realized_pnl, 6),
        "r_multiple_realized": round(r_multiple_realized, 6),
        "outcome_label": outcome_label,
        "outcome_grade": outcome_grade,
        "exit_reason": derived_exit_reason,
        "side": side,
    }


def update_trade_outcome(
    trade_id,
    exit_price,
    actual,
    exit_reason=None,
    *,
    realized_pnl_override=None,
    r_multiple_realized_override=None,
    outcome_label_override=None,
    outcome_grade_override=None,
    legs_count=None,
    avg_exit=None,
    exit_reason_final=None,
):
    path = _trade_log_path()
    from core.strategy_tracker import StrategyTracker
    tracker = StrategyTracker()
    tracker.load("logs/strategy_perf.json")
    strategy = None
    symbol = None
    side = None
    entry_price = None
    qty = None
    metrics = {}
    if getattr(cfg, "APPEND_ONLY_LOG", False) or log_lock.is_locked():
        # Append-only update record
        entry = {
            "trade_id": trade_id,
            "timestamp": str(datetime.now()),
            "type": "outcome",
            "exit_price": exit_price,
            "exit_time": str(datetime.now()),
            "actual": actual,
            "exit_reason": exit_reason,
        }
        # Compute R-multiple only if we can read the original entry
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    e = json.loads(line)
                    if e.get("trade_id") == trade_id:
                        entry_price = e.get("entry", 0)
                        stop = e.get("stop_loss", 0)
                        side = e.get("side", "BUY")
                        strategy = e.get("strategy")
                        symbol = e.get("symbol")
                        qty = e.get("qty", 1)
                        paper_aux = e.get("paper_aux", False)
                        metrics = _compute_realized_metrics(e, exit_price, actual, exit_reason=exit_reason)
                        if realized_pnl_override is not None:
                            metrics["realized_pnl"] = float(realized_pnl_override)
                        if r_multiple_realized_override is not None:
                            metrics["r_multiple_realized"] = float(r_multiple_realized_override)
                        if outcome_label_override is not None:
                            metrics["outcome_label"] = str(outcome_label_override)
                        if outcome_grade_override is not None:
                            metrics["outcome_grade"] = str(outcome_grade_override)
                        r_mult = metrics["r_multiple_realized"]
                        entry["r_multiple"] = round(r_mult, 3)
                        entry["r_label"] = 1 if r_mult >= 1 else 0
                        entry["realized_pnl"] = metrics["realized_pnl"]
                        entry["r_multiple_realized"] = metrics["r_multiple_realized"]
                        entry["outcome_label"] = metrics["outcome_label"]
                        entry["outcome_grade"] = metrics["outcome_grade"]
                        entry["exit_reason"] = metrics["exit_reason"]
                        break
        except Exception:
            pass
        _append_update(entry)
        try:
            insert_outcome(entry)
        except Exception:
            pass
        try:
            if metrics:
                update_trade_close(
                    trade_id,
                    exit_price=float(exit_price),
                    exit_time=str(entry.get("exit_time")),
                    exit_reason=metrics.get("exit_reason"),
                    realized_pnl=float(metrics.get("realized_pnl", 0.0)),
                    r_multiple_realized=float(metrics.get("r_multiple_realized", 0.0)),
                    outcome_label=metrics.get("outcome_label", "BREAKEVEN"),
                    outcome_grade=metrics.get("outcome_grade", "C"),
                    legs_count=legs_count,
                    avg_exit=avg_exit,
                    exit_reason_final=exit_reason_final,
                )
        except Exception as exc:
            _log_error({"error": "update_trade_close_failed", "trade_id": trade_id, "detail": str(exc)})
        try:
            if entry.get("actual") is not None:
                _safe_emit_post_trade_label(entry)
        except Exception:
            pass
        try:
            if entry_price is not None and qty is not None and not paper_aux:
                pnl = (exit_price - entry_price) * qty
                if side == "SELL":
                    pnl *= -1
                tracker.record(strategy, pnl)
                tracker.record_symbol(symbol, pnl)
                tracker.save("logs/strategy_perf.json")
        except Exception:
            pass
        return entry

    updated = False
    lines = []
    updated_entry = None

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("trade_id") == trade_id:
                entry["exit_price"] = exit_price
                entry["exit_time"] = str(datetime.now())
                entry["actual"] = actual
                entry["exit_reason"] = exit_reason
                # Risk-adjusted label (R-multiple)
                entry_price = entry.get("entry", 0)
                strategy = entry.get("strategy")
                symbol = entry.get("symbol")
                side = entry.get("side", "BUY")
                qty = entry.get("qty", 1)
                paper_aux = entry.get("paper_aux", False)
                metrics = _compute_realized_metrics(entry, exit_price, actual, exit_reason=exit_reason)
                if realized_pnl_override is not None:
                    metrics["realized_pnl"] = float(realized_pnl_override)
                if r_multiple_realized_override is not None:
                    metrics["r_multiple_realized"] = float(r_multiple_realized_override)
                if outcome_label_override is not None:
                    metrics["outcome_label"] = str(outcome_label_override)
                if outcome_grade_override is not None:
                    metrics["outcome_grade"] = str(outcome_grade_override)
                r_mult = metrics["r_multiple_realized"]
                entry["r_multiple"] = round(r_mult, 3)
                entry["r_label"] = 1 if r_mult >= 1 else 0
                entry["realized_pnl"] = metrics["realized_pnl"]
                entry["r_multiple_realized"] = metrics["r_multiple_realized"]
                entry["outcome_label"] = metrics["outcome_label"]
                entry["outcome_grade"] = metrics["outcome_grade"]
                entry["exit_reason"] = metrics["exit_reason"]
                updated = True
                updated_entry = entry
            lines.append(json.dumps(entry))

    if updated:
        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    if updated_entry:
        try:
            insert_outcome(updated_entry)
        except Exception:
            pass
        try:
            update_trade_close(
                trade_id,
                exit_price=float(exit_price),
                exit_time=str(updated_entry.get("exit_time")),
                exit_reason=updated_entry.get("exit_reason") or ("TARGET" if actual == 1 else "STOP"),
                realized_pnl=float(updated_entry.get("realized_pnl", 0.0)),
                r_multiple_realized=float(updated_entry.get("r_multiple_realized", 0.0)),
                outcome_label=updated_entry.get("outcome_label", "BREAKEVEN"),
                outcome_grade=updated_entry.get("outcome_grade", "C"),
                legs_count=legs_count,
                avg_exit=avg_exit,
                exit_reason_final=exit_reason_final,
            )
        except Exception as exc:
            _log_error({"error": "update_trade_close_failed", "trade_id": trade_id, "detail": str(exc)})
        try:
            if updated_entry.get("actual") is not None:
                _safe_emit_post_trade_label(updated_entry)
        except Exception:
            pass
        try:
            if entry_price is not None and qty is not None and not paper_aux:
                pnl = (exit_price - entry_price) * qty
                if side == "SELL":
                    pnl *= -1
                tracker.record(strategy, pnl)
                tracker.record_symbol(symbol, pnl)
                tracker.save("logs/strategy_perf.json")
        except Exception:
            pass
    return updated_entry if updated else None

def update_trade_fill(trade_id, fill_price, latency_ms=None, slippage=None):
    path = _trade_log_path()
    if getattr(cfg, "APPEND_ONLY_LOG", False) or log_lock.is_locked():
        entry = {
            "trade_id": trade_id,
            "timestamp": str(datetime.now()),
            "type": "fill",
            "fill_price": fill_price,
        }
        if latency_ms is not None:
            entry["latency_ms"] = latency_ms
        if slippage is not None:
            entry["slippage"] = slippage
        _append_update(entry)
        try:
            update_trade_fill_db(trade_id, fill_price, latency_ms=latency_ms, slippage=slippage)
        except Exception:
            pass
        return entry

    updated = False
    lines = []
    updated_entry = None

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("trade_id") == trade_id:
                entry["fill_price"] = fill_price
                if latency_ms is not None:
                    entry["latency_ms"] = latency_ms
                if slippage is not None:
                    entry["slippage"] = slippage
                updated = True
                updated_entry = entry
            lines.append(json.dumps(entry))

    if updated:
        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    if updated_entry:
        try:
            update_trade_fill_db(trade_id, fill_price, latency_ms=latency_ms, slippage=slippage)
        except Exception:
            pass
    return updated_entry if updated else None

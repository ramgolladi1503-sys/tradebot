from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from core.events import write_json_atomic
from core.paths import logs_dir, repo_logs_dir, runtime_dir


RUNTIME_STRATEGY_NO_QUALIFIED_REASONS_SCHEMA_VERSION = 1
RUNTIME_STRATEGY_NO_QUALIFIED_REASONS_SOURCE = "runtime_strategy_no_qualified_reasons_v1"
RUNTIME_STRATEGY_NO_QUALIFIED_REASONS_FILENAME = "strategy_no_qualified_reasons_latest.json"

REASON_CATEGORIES = {
    "vwap",
    "breakout",
    "atr",
    "adx",
    "volume",
    "liquidity",
    "option_chain_confirmation",
    "expiry_restriction",
    "spread",
    "direction_or_regime_mismatch",
    "quote_quality",
    "unknown",
}

FEED_BLOCKERS = {
    "FEED_LTP_STALE",
    "FEED_DEPTH_STALE",
    "FEED_STALE",
    "OPTION_TICK_STALE",
    "STALE_INDEX",
    "STALE_OPTION_LTP",
    "QUOTE_AGE_STALE",
}
INDICATOR_BLOCKERS = {"INDICATORS_MISSING"}
REGIME_BLOCKERS = {"REGIME_UNSTABLE"}


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if value in (None, "", "None"):
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _strategy_id(value: Any) -> str:
    strategy = str(value or "").strip()
    return strategy.upper() if strategy else "unknown"


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_bool(value: Any) -> bool:
    try:
        return bool(value)
    except Exception:
        return False


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item or "").strip()]


def _infer_indicator_ready(irow: Mapping[str, Any] | None) -> bool | None:
    if not isinstance(irow, Mapping):
        return None
    if "ready" in irow:
        return _safe_bool(irow.get("ready"))
    if "indicators_ok" in irow:
        return _safe_bool(irow.get("indicators_ok"))
    missing = [item.lower() for item in _string_list(irow.get("indicator_missing_inputs"))]
    if missing:
        return False
    present_keys = ("rsi_present", "ema_present", "atr_present", "vwap_present")
    if any(key in irow for key in present_keys):
        return all(_safe_bool(irow.get(key)) for key in present_keys if key in irow)
    return None


def _infer_regime_blocked(sym: str, regime_truth: Mapping[str, Any] | None) -> bool:
    regime = _as_mapping(regime_truth)
    by_symbol = regime.get("by_symbol") if isinstance(regime.get("by_symbol"), Mapping) else {}
    row = by_symbol.get(sym) if isinstance(by_symbol, Mapping) else None
    if isinstance(row, Mapping):
        if _string_list(row.get("unstable_reasons")):
            return True
        if row.get("regime_ok") is False:
            return True
        if _upper(row.get("decision_gate_reason")) == "REGIME_UNSTABLE":
            return True
    gates = regime.get("gate_reasons") if isinstance(regime.get("gate_reasons"), Mapping) else {}
    return _safe_int(_as_mapping(gates).get("REGIME_UNSTABLE")) > 0 and sym in _as_mapping(by_symbol)


def classify_no_qualified_reason_category(*values: Any) -> str:
    text = " ".join(str(value or "") for value in values if value is not None).strip().lower()
    if not text:
        return "unknown"
    compact = text.replace("-", "_").replace(" ", "_")
    if "vwap" in compact:
        return "vwap"
    if "breakout" in compact or "orb" in compact:
        return "breakout"
    if "atr" in compact:
        return "atr"
    if "adx" in compact:
        return "adx"
    if "volume" in compact or compact == "vol" or "low_vol" in compact:
        return "volume"
    if "liquid" in compact:
        return "liquidity"
    if "option_chain" in compact or "chain_confirmation" in compact or "oi_confirm" in compact:
        return "option_chain_confirmation"
    if "expiry" in compact or "time_window" in compact or "window" in compact:
        return "expiry_restriction"
    if "spread" in compact or "bidask" in compact or "bid_ask" in compact:
        return "spread"
    if "regime" in compact or "direction" in compact or "trend_mismatch" in compact:
        return "direction_or_regime_mismatch"
    if "quote" in compact or "stale" in compact or "ltp" in compact:
        return "quote_quality"
    return "unknown"


def _first_reason(*values: Any) -> str:
    for value in values:
        for item in _string_list(value):
            if item:
                return item
    return "unknown"


def build_strategy_attempt_from_gate(
    *,
    symbol: str,
    strategy_id: str | None,
    gate_reasons: Any,
    telemetry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    tele = _as_mapping(telemetry)
    fail_codes = _string_list(tele.get("qual_fail_codes"))
    raw_reasons = _string_list(tele.get("qual_fail_reasons_raw"))
    picked = tele.get("picked_candidate") if isinstance(tele.get("picked_candidate"), Mapping) else {}
    all_candidates = tele.get("all_candidates") if isinstance(tele.get("all_candidates"), list) else []
    candidate_produced = bool(all_candidates)
    no_setup_reason = _first_reason(raw_reasons, fail_codes, gate_reasons, "NO_STRATEGY_QUALIFIED")
    category = classify_no_qualified_reason_category(fail_codes, raw_reasons, gate_reasons, picked)
    strategy = _strategy_id(strategy_id or picked.get("family"))
    return {
        "symbol": _upper(symbol),
        "strategy_id": strategy,
        "attempted": True,
        "trade_builder_ran": False,
        "candidate_produced": candidate_produced,
        "candidate_generated_then_dropped": False,
        "no_setup_qualified": not candidate_produced,
        "no_setup_reason": no_setup_reason,
        "reason_category": category if category in REASON_CATEGORIES else "unknown",
        "gate_reasons": _string_list(gate_reasons),
        "qual_fail_codes": fail_codes,
        "qual_fail_reasons_raw": raw_reasons,
        "raw_candidate_count": 0,
        "post_scan_survivor_count": 0,
        "source": "strategy_gate",
    }


def build_strategy_attempt_from_trade_builder(
    *,
    symbol: str,
    strategy_id: str | None,
    raw_candidate_count: int | None,
    post_scan_survivor_count: int | None,
    trade_generated: bool,
    reject_reason: str | None,
    reject_gate_reasons: Any,
) -> dict[str, Any]:
    raw_count = _safe_int(raw_candidate_count)
    survivor_count = _safe_int(post_scan_survivor_count)
    produced = bool(trade_generated)
    generated_then_dropped = raw_count > 0 and not produced
    reasons = _string_list(reject_gate_reasons)
    no_setup_reason = _first_reason(reject_reason, reasons, "trade_builder_no_candidate")
    category = classify_no_qualified_reason_category(reject_reason, reasons)
    return {
        "symbol": _upper(symbol),
        "strategy_id": _strategy_id(strategy_id),
        "attempted": True,
        "trade_builder_ran": True,
        "candidate_produced": produced,
        "candidate_generated_then_dropped": generated_then_dropped,
        "no_setup_qualified": raw_count == 0 and not produced,
        "no_setup_reason": no_setup_reason,
        "reason_category": category if category in REASON_CATEGORIES else "unknown",
        "gate_reasons": reasons,
        "qual_fail_codes": [],
        "qual_fail_reasons_raw": [str(reject_reason).strip()] if str(reject_reason or "").strip() else [],
        "raw_candidate_count": raw_count,
        "post_scan_survivor_count": survivor_count,
        "source": "trade_builder",
    }


def _market_symbols(market_data_list: list[Mapping[str, Any]] | None) -> list[str]:
    symbols: list[str] = []
    for row in list(market_data_list or []):
        if not isinstance(row, Mapping):
            continue
        symbol = _upper(row.get("symbol"))
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def _prepared_attempts(strategy_attempts: list[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attempt in list(strategy_attempts or []):
        if not isinstance(attempt, Mapping):
            continue
        row = dict(attempt)
        row["symbol"] = _upper(row.get("symbol"))
        row["strategy_id"] = _strategy_id(None if str(row.get("strategy_id") or "").strip().lower() == "unknown" else row.get("strategy_id"))
        row["attempted"] = _safe_bool(row.get("attempted", True))
        row["trade_builder_ran"] = _safe_bool(row.get("trade_builder_ran"))
        row["candidate_produced"] = _safe_bool(row.get("candidate_produced"))
        row["candidate_generated_then_dropped"] = _safe_bool(row.get("candidate_generated_then_dropped"))
        row["no_setup_qualified"] = _safe_bool(row.get("no_setup_qualified"))
        row["no_setup_reason"] = str(row.get("no_setup_reason") or "unknown").strip() or "unknown"
        row["reason_category"] = (
            str(row.get("reason_category") or "unknown").strip().lower() or "unknown"
        )
        if row["reason_category"] not in REASON_CATEGORIES:
            row["reason_category"] = "unknown"
        row["gate_reasons"] = _string_list(row.get("gate_reasons"))
        row["qual_fail_codes"] = _string_list(row.get("qual_fail_codes"))
        row["qual_fail_reasons_raw"] = _string_list(row.get("qual_fail_reasons_raw"))
        row["raw_candidate_count"] = _safe_int(row.get("raw_candidate_count"))
        row["post_scan_survivor_count"] = _safe_int(row.get("post_scan_survivor_count"))
        row["source"] = str(row.get("source") or "unknown").strip() or "unknown"
        if row["symbol"]:
            rows.append(row)
    return rows


def _blocked_reason(
    *,
    blockers: Mapping[str, Any],
    symbols: list[str],
    indicator_readiness: Mapping[str, Any] | None,
    regime_truth: Mapping[str, Any] | None,
    raw_candidate_count: int | None,
    phase2_input_candidate_count: int | None,
) -> str | None:
    blocker_codes = {_upper(key) for key, value in blockers.items() if _safe_int(value) > 0}
    if blocker_codes.intersection(FEED_BLOCKERS):
        return "feed_blocked"

    indicator = _as_mapping(indicator_readiness)
    indicator_by_symbol = indicator.get("by_symbol") if isinstance(indicator.get("by_symbol"), Mapping) else {}
    blocked_indicators = 0
    for symbol in symbols:
        ready = _infer_indicator_ready(_as_mapping(indicator_by_symbol).get(symbol))
        if ready is False:
            blocked_indicators += 1
    if blocked_indicators > 0 or blocker_codes.intersection(INDICATOR_BLOCKERS):
        return "indicator_blocked"

    blocked_regimes = sum(1 for symbol in symbols if _infer_regime_blocked(symbol, regime_truth))
    if blocked_regimes > 0 or blocker_codes.intersection(REGIME_BLOCKERS):
        return "regime_blocked"

    if _safe_int(phase2_input_candidate_count) > 0:
        return "candidates_reached_phase2"
    if raw_candidate_count is not None and _safe_int(raw_candidate_count) > 0:
        return "candidates_generated_then_dropped"
    if "NO_STRATEGY_QUALIFIED" not in blocker_codes:
        return "no_no_strategy_qualified_gate"
    return None


def build_strategy_no_qualified_reasons_payload(
    *,
    execution_mode: str | None,
    market_open: bool | None,
    market_data_list: list[Mapping[str, Any]] | None,
    cycle_blockers: Mapping[str, Any] | None,
    indicator_readiness: Mapping[str, Any] | None,
    regime_truth: Mapping[str, Any] | None,
    strategy_attempts: list[Mapping[str, Any]] | None,
    raw_candidate_count: int | None,
    phase2_input_candidate_count: int | None,
) -> dict[str, Any]:
    symbols = _market_symbols(market_data_list)
    attempts = _prepared_attempts(strategy_attempts)
    blockers = _as_mapping(cycle_blockers)
    raw_count = None if raw_candidate_count is None else _safe_int(raw_candidate_count)
    phase2_count = None if phase2_input_candidate_count is None else _safe_int(phase2_input_candidate_count)
    not_applicable_reason = _blocked_reason(
        blockers=blockers,
        symbols=symbols,
        indicator_readiness=indicator_readiness,
        regime_truth=regime_truth,
        raw_candidate_count=raw_count,
        phase2_input_candidate_count=phase2_count,
    )
    by_symbol: dict[str, Any] = {
        symbol: {
            "attempt_count": 0,
            "strategies_attempted": [],
            "trade_builder_ran": False,
            "candidate_produced_count": 0,
            "candidate_generated_then_dropped_count": 0,
            "no_setup_qualified_count": 0,
            "reason_categories": {},
            "attempts": [],
        }
        for symbol in symbols
    }
    by_strategy: dict[str, Any] = {}
    categories = Counter()
    no_setup_count = 0
    generated_then_dropped_count = 0
    for attempt in attempts:
        symbol = str(attempt.get("symbol") or "")
        strategy = str(attempt.get("strategy_id") or "unknown")
        by_symbol.setdefault(
            symbol,
            {
                "attempt_count": 0,
                "strategies_attempted": [],
                "trade_builder_ran": False,
                "candidate_produced_count": 0,
                "candidate_generated_then_dropped_count": 0,
                "no_setup_qualified_count": 0,
                "reason_categories": {},
                "attempts": [],
            },
        )
        by_strategy.setdefault(
            strategy,
            {
                "attempt_count": 0,
                "symbols": [],
                "trade_builder_ran_count": 0,
                "candidate_produced_count": 0,
                "candidate_generated_then_dropped_count": 0,
                "no_setup_qualified_count": 0,
                "reason_categories": {},
            },
        )
        category = str(attempt.get("reason_category") or "unknown")
        categories[category] += 1
        by_symbol[symbol]["attempt_count"] += 1
        if strategy not in by_symbol[symbol]["strategies_attempted"]:
            by_symbol[symbol]["strategies_attempted"].append(strategy)
        by_symbol[symbol]["trade_builder_ran"] = bool(
            by_symbol[symbol]["trade_builder_ran"] or attempt.get("trade_builder_ran")
        )
        by_symbol[symbol]["candidate_produced_count"] += 1 if attempt.get("candidate_produced") else 0
        by_symbol[symbol]["candidate_generated_then_dropped_count"] += (
            1 if attempt.get("candidate_generated_then_dropped") else 0
        )
        by_symbol[symbol]["no_setup_qualified_count"] += 1 if attempt.get("no_setup_qualified") else 0
        by_symbol[symbol]["reason_categories"][category] = (
            _safe_int(by_symbol[symbol]["reason_categories"].get(category)) + 1
        )
        by_symbol[symbol]["attempts"].append(dict(attempt))

        by_strategy[strategy]["attempt_count"] += 1
        if symbol not in by_strategy[strategy]["symbols"]:
            by_strategy[strategy]["symbols"].append(symbol)
        by_strategy[strategy]["trade_builder_ran_count"] += 1 if attempt.get("trade_builder_ran") else 0
        by_strategy[strategy]["candidate_produced_count"] += 1 if attempt.get("candidate_produced") else 0
        by_strategy[strategy]["candidate_generated_then_dropped_count"] += (
            1 if attempt.get("candidate_generated_then_dropped") else 0
        )
        by_strategy[strategy]["no_setup_qualified_count"] += 1 if attempt.get("no_setup_qualified") else 0
        by_strategy[strategy]["reason_categories"][category] = (
            _safe_int(by_strategy[strategy]["reason_categories"].get(category)) + 1
        )
        no_setup_count += 1 if attempt.get("no_setup_qualified") else 0
        generated_then_dropped_count += 1 if attempt.get("candidate_generated_then_dropped") else 0

    payload = {
        "schema_version": RUNTIME_STRATEGY_NO_QUALIFIED_REASONS_SCHEMA_VERSION,
        "source": RUNTIME_STRATEGY_NO_QUALIFIED_REASONS_SOURCE,
        "writer_name": "runtime_strategy_no_qualified_reasons",
        "writer_module": __name__,
        "writer_schema_version": RUNTIME_STRATEGY_NO_QUALIFIED_REASONS_SCHEMA_VERSION,
        "generated_epoch": float(time.time()),
        "execution_mode": _upper(execution_mode) or "SIM",
        "market_open": bool(market_open) if market_open is not None else None,
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_allowed": False,
        "strategy_no_qualified_applicable": not_applicable_reason is None,
        "not_applicable_reason": not_applicable_reason,
        "raw_candidate_count": raw_count,
        "phase2_input_candidate_count": phase2_count,
        "symbols_evaluated": list(symbols),
        "symbol_count": int(len(symbols)),
        "strategies_attempted": sorted({str(row.get("strategy_id") or "unknown") for row in attempts}),
        "strategy_generation_attempt_count": int(len(attempts)),
        "no_setup_qualified_count": int(no_setup_count),
        "candidate_generated_then_dropped_count": int(generated_then_dropped_count),
        "reason_categories": dict(categories),
        "unknown_reason_count": int(categories.get("unknown", 0)),
        "gate_reasons": {
            _upper(key): _safe_int(value)
            for key, value in blockers.items()
            if _upper(key) and _safe_int(value) > 0
        },
        "by_symbol": dict(by_symbol),
        "by_strategy": dict(by_strategy),
        "notes": [
            "Evidence-only trace. Does not change gates, strategies, ranking, Phase2, broker, or order behavior.",
            "Unknown classification is used when evidence is insufficient; categories are not inferred beyond explicit reason text/codes.",
        ],
    }
    return json.loads(json.dumps(payload, ensure_ascii=True, default=str))


def write_strategy_no_qualified_reasons_latest(
    *,
    payload: Mapping[str, Any],
    logs_path: Path | None = None,
    runtime_path: Path | None = None,
    runtime_logs_path: Path | None = None,
) -> tuple[Path, Path, Path]:
    logs_target = (
        Path(logs_path)
        if logs_path is not None
        else (repo_logs_dir() / RUNTIME_STRATEGY_NO_QUALIFIED_REASONS_FILENAME)
    )
    runtime_target = (
        Path(runtime_path)
        if runtime_path is not None
        else (runtime_dir() / RUNTIME_STRATEGY_NO_QUALIFIED_REASONS_FILENAME)
    )
    runtime_logs_target = (
        Path(runtime_logs_path)
        if runtime_logs_path is not None
        else (logs_dir() / RUNTIME_STRATEGY_NO_QUALIFIED_REASONS_FILENAME)
    )
    logs_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_logs_target.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload) if isinstance(payload, Mapping) else {}
    write_json_atomic(logs_target, out)
    write_json_atomic(runtime_target, out)
    write_json_atomic(runtime_logs_target, out)
    return logs_target, runtime_target, runtime_logs_target


__all__ = [
    "RUNTIME_STRATEGY_NO_QUALIFIED_REASONS_FILENAME",
    "build_strategy_attempt_from_gate",
    "build_strategy_attempt_from_trade_builder",
    "build_strategy_no_qualified_reasons_payload",
    "classify_no_qualified_reason_category",
    "write_strategy_no_qualified_reasons_latest",
]

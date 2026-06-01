from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from core.events import write_json_atomic
from core.paths import logs_dir, repo_logs_dir, runtime_dir


RUNTIME_CANDIDATE_FLOW_TRACE_SCHEMA_VERSION = 1
RUNTIME_CANDIDATE_FLOW_TRACE_SOURCE = "runtime_candidate_flow_trace_v1"
RUNTIME_CANDIDATE_FLOW_TRACE_FILENAME = "candidate_flow_trace_latest.json"


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if value in (None, "", "None"):
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _infer_indicator_ready(irow: Mapping[str, Any] | None) -> bool | None:
    if not isinstance(irow, Mapping):
        return None

    # Preferred explicit key when present.
    if "ready" in irow:
        try:
            return bool(irow.get("ready"))
        except Exception:
            return None

    # Contract-compatible: readiness v2 uses "indicators_ok".
    if "indicators_ok" in irow:
        try:
            return bool(irow.get("indicators_ok"))
        except Exception:
            return None

    missing_list = [str(x).strip().lower() for x in _as_list(irow.get("indicator_missing_inputs")) if str(x or "").strip()]
    if missing_list:
        return False

    # Best-effort: infer from present flags if they exist and missing list is empty.
    present_keys = ("rsi_present", "ema_present", "atr_present", "vwap_present")
    if any(k in irow for k in present_keys):
        try:
            flags_ok = all(bool(irow.get(k)) for k in present_keys if k in irow)
        except Exception:
            flags_ok = False
        return True if flags_ok else False

    return None


def _infer_regime_blocked(
    *,
    sym: str,
    regime_by_symbol: Mapping[str, Any] | None,
    regime_gate_reasons: Mapping[str, Any] | None,
    decision_gate_reason_by_symbol: Mapping[str, Any] | None = None,
) -> bool | None:
    # Do not treat mere dict presence as blocked. Only explicit unstable/reject evidence counts.
    by_symbol = dict(regime_by_symbol or {})
    rrow = by_symbol.get(sym)
    if isinstance(rrow, Mapping):
        unstable = rrow.get("unstable_reasons")
        if isinstance(unstable, list) and len(unstable) > 0:
            return True
        if "regime_ok" in rrow and rrow.get("regime_ok") is False:
            return True

    gates = dict(regime_gate_reasons or {})
    if _safe_int(gates.get("REGIME_UNSTABLE")) > 0:
        # If we have per-symbol regime evidence and this symbol appears there, treat it as blocked.
        # Otherwise keep it unknown; do not smear global gate into every symbol.
        return True if sym in by_symbol else None

    if decision_gate_reason_by_symbol is not None:
        code = _upper(dict(decision_gate_reason_by_symbol).get(sym))
        if code == "REGIME_UNSTABLE":
            return True

    return False


def build_candidate_flow_trace_payload(
    *,
    execution_mode: str | None,
    market_open: bool | None,
    market_data_list: list[Mapping[str, Any]] | None,
    cycle_blockers: Mapping[str, Any] | None,
    indicator_readiness: Mapping[str, Any] | None,
    regime_truth: Mapping[str, Any] | None,
    raw_candidate_count: int | None,
    phase2_input_candidate_count: int | None,
    decision_gate_reason_by_symbol: Mapping[str, Any] | None = None,
    # Optional stage drop counts are evidence-only; emit None when unknown.
    validation_drop_count: int | None = None,
    normalization_drop_count: int | None = None,
    dedup_drop_count: int | None = None,
) -> dict[str, Any]:
    mode = _upper(execution_mode) or "SIM"
    md_list = list(market_data_list or [])
    blockers = _as_mapping(cycle_blockers)
    indicator = _as_mapping(indicator_readiness)
    regime = _as_mapping(regime_truth)

    symbols: list[str] = []
    by_symbol: dict[str, Any] = {}
    for row in md_list:
        if not isinstance(row, Mapping):
            continue
        sym = _upper(row.get("symbol"))
        if not sym:
            continue
        if sym not in symbols:
            symbols.append(sym)
        by_symbol.setdefault(sym, {})

    indicator_by_symbol = indicator.get("by_symbol") if isinstance(indicator.get("by_symbol"), Mapping) else {}
    indicator_ready_symbol_count = 0
    indicator_blocked_symbol_count = 0
    for sym in symbols:
        irow = indicator_by_symbol.get(sym) if isinstance(indicator_by_symbol, Mapping) else None
        ready = _infer_indicator_ready(irow) if isinstance(irow, Mapping) else None
        if ready is True:
            indicator_ready_symbol_count += 1
        elif ready is False:
            indicator_blocked_symbol_count += 1
        by_symbol[sym]["indicator_ready"] = ready

    regime_by_symbol = regime.get("by_symbol") if isinstance(regime.get("by_symbol"), Mapping) else {}
    regime_gate_reasons = regime.get("gate_reasons") if isinstance(regime.get("gate_reasons"), Mapping) else {}
    regime_ready_symbol_count = 0
    regime_blocked_symbol_count = 0
    for sym in symbols:
        blocked = _infer_regime_blocked(
            sym=sym,
            regime_by_symbol=regime_by_symbol if isinstance(regime_by_symbol, Mapping) else {},
            regime_gate_reasons=regime_gate_reasons if isinstance(regime_gate_reasons, Mapping) else {},
            decision_gate_reason_by_symbol=decision_gate_reason_by_symbol if isinstance(decision_gate_reason_by_symbol, Mapping) else None,
        )
        if blocked is True:
            regime_blocked_symbol_count += 1
        else:
            regime_ready_symbol_count += 1
        by_symbol[sym]["regime_blocked"] = blocked

    gate_reasons: Counter[str] = Counter()
    for k, v in blockers.items():
        code = _upper(k)
        if not code:
            continue
        try:
            count = int(v or 0)
        except Exception:
            count = 1
        if count <= 0:
            continue
        gate_reasons[code] += count

    raw_count = None if raw_candidate_count is None else _safe_int(raw_candidate_count)
    phase2_count = None if phase2_input_candidate_count is None else _safe_int(phase2_input_candidate_count)

    # First-zero-stage inference is evidence-only. Prefer explicit stage counts if provided.
    first_zero_stage = "unknown"
    if len(symbols) == 0:
        first_zero_stage = "no_market_data"
    elif indicator_ready_symbol_count == 0 and indicator_blocked_symbol_count > 0:
        first_zero_stage = "indicators_blocked"
    elif indicator_ready_symbol_count > 0 and regime_ready_symbol_count == 0 and regime_blocked_symbol_count > 0:
        first_zero_stage = "regime_blocked"
    elif raw_count == 0:
        first_zero_stage = "strategy_generation_zero"
    elif raw_count is not None and raw_count > 0 and phase2_count == 0:
        if validation_drop_count is not None and _safe_int(validation_drop_count) >= raw_count:
            first_zero_stage = "validation_dropped_all"
        elif normalization_drop_count is not None and _safe_int(normalization_drop_count) >= raw_count:
            first_zero_stage = "normalization_dropped_all"
        elif dedup_drop_count is not None and _safe_int(dedup_drop_count) >= raw_count:
            first_zero_stage = "dedup_dropped_all"
        else:
            first_zero_stage = "phase2_adapter_empty"
    elif phase2_count is not None and phase2_count > 0:
        first_zero_stage = "not_starved"

    starvation_summary = {
        "notes": [
            "Evidence-only trace. Does not change any gates, strategies, ranking, or Phase2 behavior.",
            "Drop counts are None unless explicitly provided by the orchestrator.",
        ],
        "missing_counts_reason": None
        if (validation_drop_count is not None or normalization_drop_count is not None or dedup_drop_count is not None)
        else "orchestrator_does_not_expose_drop_stage_counts",
    }

    payload = {
        "schema_version": RUNTIME_CANDIDATE_FLOW_TRACE_SCHEMA_VERSION,
        "source": RUNTIME_CANDIDATE_FLOW_TRACE_SOURCE,
        "writer_name": "runtime_candidate_flow_trace",
        "writer_module": __name__,
        "writer_schema_version": RUNTIME_CANDIDATE_FLOW_TRACE_SCHEMA_VERSION,
        "generated_epoch": float(time.time()),
        "execution_mode": mode,
        "market_open": bool(market_open) if market_open is not None else None,
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        # counts
        "market_data_symbol_count": int(len(symbols)),
        "market_data_symbols": list(symbols),
        "indicator_ready_symbol_count": int(indicator_ready_symbol_count),
        "indicator_blocked_symbol_count": int(indicator_blocked_symbol_count),
        "regime_ready_symbol_count": int(regime_ready_symbol_count),
        "regime_blocked_symbol_count": int(regime_blocked_symbol_count),
        "strategy_generation_attempt_count": None,
        "raw_candidate_count": raw_count,
        "validation_drop_count": validation_drop_count,
        "normalization_drop_count": normalization_drop_count,
        "dedup_drop_count": dedup_drop_count,
        "phase2_input_candidate_count": phase2_count,
        # details
        "by_symbol": dict(by_symbol),
        "by_strategy": {},
        "drop_reasons": {},
        "gate_reasons": dict(gate_reasons),
        "first_zero_stage": str(first_zero_stage),
        "starvation_summary": dict(starvation_summary),
    }
    return json.loads(json.dumps(payload, ensure_ascii=True, default=str))


def write_candidate_flow_trace_latest(
    *,
    payload: Mapping[str, Any],
    logs_path: Path | None = None,
    runtime_path: Path | None = None,
) -> tuple[Path, Path]:
    logs_target = Path(logs_path) if logs_path is not None else (repo_logs_dir() / RUNTIME_CANDIDATE_FLOW_TRACE_FILENAME)
    runtime_target = Path(runtime_path) if runtime_path is not None else (runtime_dir() / RUNTIME_CANDIDATE_FLOW_TRACE_FILENAME)
    runtime_logs_target = logs_dir() / RUNTIME_CANDIDATE_FLOW_TRACE_FILENAME
    logs_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_logs_target.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload) if isinstance(payload, Mapping) else {}
    write_json_atomic(logs_target, out)
    write_json_atomic(runtime_target, out)
    write_json_atomic(runtime_logs_target, out)
    return logs_target, runtime_target


__all__ = [
    "RUNTIME_CANDIDATE_FLOW_TRACE_FILENAME",
    "build_candidate_flow_trace_payload",
    "write_candidate_flow_trace_latest",
]

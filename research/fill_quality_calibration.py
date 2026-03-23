from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from config import config as cfg
from core.fill_quality import FILL_LOG_PATH
from core.fill_quality_profile import FillQualityProfile, build_fill_quality_profiles, profile_rows
from core.paths import logs_dir
from core.trade_log_paths import resolve_trade_log_path
from research.setup_expectancy import _coerce_epoch_ms, _iter_jsonl, _json_dict, _safe_float, _write_report


PROFILE_COLUMNS = [
    "symbol",
    "premium_bucket",
    "liquidity_bucket",
    "time_bucket",
    "trade_count",
    "filled_trade_count",
    "fill_rate",
    "expected_fill_deviation",
    "slippage_multiplier",
    "fill_confidence",
    "avg_reference_deviation",
    "reference_trade_count",
]


def _trade_id(row: Mapping[str, Any]) -> str | None:
    for key in ("trade_id", "decision_trace_id", "trace_id", "advisory_id"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return None


def _path_or_default(path: Path | None, default: Path) -> Path:
    return Path(path) if path is not None else Path(default)


def _fill_quality_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("fill_quality")
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except Exception:
            decoded = None
        if isinstance(decoded, dict):
            return dict(decoded)
    json_payload = _json_dict(row.get("fill_quality_json"))
    return json_payload if isinstance(json_payload, dict) else {}


def _depth_best(row: Mapping[str, Any]) -> float | None:
    direct = (
        _safe_float(row.get("depth_best"))
        or _safe_float(row.get("top_depth_qty"))
        or _safe_float(row.get("depth_qty"))
    )
    if direct is not None:
        return direct
    depth_summary = row.get("depth_summary")
    if isinstance(depth_summary, dict):
        best = max(
            _safe_float(depth_summary.get("best_bid_qty")) or 0.0,
            _safe_float(depth_summary.get("best_ask_qty")) or 0.0,
        )
        if best > 0:
            return best
    debug = row.get("debug")
    if isinstance(debug, dict):
        return _safe_float(debug.get("depth_best"))
    return None


def _base_context(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "trade_id": _trade_id(row),
        "symbol": str(row.get("symbol") or row.get("underlying") or "UNKNOWN").strip().upper() or "UNKNOWN",
        "timestamp": row.get("timestamp"),
        "timestamp_epoch_ms": (
            _coerce_epoch_ms(row.get("timestamp_epoch_ms"))
            or _coerce_epoch_ms(row.get("ts_epoch_ms"))
            or _coerce_epoch_ms(row.get("ts_epoch"))
            or _coerce_epoch_ms(row.get("timestamp"))
            or _coerce_epoch_ms(row.get("trade_lifecycle_ts"))
        ),
        "entry_price": (
            _safe_float(row.get("entry"))
            or _safe_float(row.get("entry_price"))
            or _safe_float(row.get("expected_entry"))
            or _safe_float(row.get("execution_entry"))
        ),
        "expected_slippage": _safe_float(row.get("expected_slippage")),
        "volume": _safe_float(row.get("volume")) or _safe_float(row.get("current_volume")),
        "qty": _safe_float(row.get("qty_units")) or _safe_float(row.get("qty")),
        "decision_bid": _safe_float(row.get("decision_bid")) or _safe_float(row.get("opt_bid")) or _safe_float(row.get("best_bid")),
        "decision_ask": _safe_float(row.get("decision_ask")) or _safe_float(row.get("opt_ask")) or _safe_float(row.get("best_ask")),
        "quote_ok": row.get("quote_ok", True),
        "depth_best": _depth_best(row),
        "fill_price": _safe_float(row.get("fill_price")),
        "slippage": _safe_float(row.get("slippage")),
        "slippage_vs_mid": _safe_float(row.get("slippage_vs_mid")),
        "filled": row.get("filled_bool"),
    }


def _merge_missing(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if key not in target or target.get(key) in (None, "", "UNKNOWN"):
            if value not in (None, "", "UNKNOWN"):
                target[key] = value


def _execution_perf_hints(rows: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    hints: dict[str, tuple[int, float]] = {}
    for row in rows:
        instrument = str(row.get("instrument") or "").strip().upper()
        fill_rate = _safe_float(row.get("fill_rate"))
        sample_size = int(_safe_float(row.get("sample_size")) or 0)
        if not instrument or fill_rate is None:
            continue
        normalized_fill_rate = float(fill_rate)
        if normalized_fill_rate > 1.0:
            normalized_fill_rate = normalized_fill_rate / 100.0
        current = hints.get(instrument)
        if current is None or sample_size >= current[0]:
            hints[instrument] = (sample_size, max(0.0, min(1.0, normalized_fill_rate)))
    return {key: value[1] for key, value in hints.items()}


def _apply_execution_performance_hints(
    profiles: list[FillQualityProfile],
    perf_hints: Mapping[str, float],
) -> tuple[list[FillQualityProfile], int]:
    if not profiles or not perf_hints:
        return list(profiles), 0
    adjusted: list[FillQualityProfile] = []
    matched = 0
    for profile in profiles:
        hint = perf_hints.get(profile.symbol)
        if hint is None:
            adjusted.append(profile)
            continue
        matched += 1
        adjusted.append(
            replace(
                profile,
                fill_confidence=round(
                    max(0.0, min(1.0, (float(profile.fill_confidence) * 0.7) + (float(hint) * 0.3))),
                    6,
                ),
            )
        )
    return adjusted, matched


def load_fill_quality_calibration_rows(
    *,
    fill_quality_path: Path | None = None,
    trade_log_path: Path | None = None,
    trade_updates_path: Path | None = None,
) -> list[dict[str, Any]]:
    fill_path = _path_or_default(fill_quality_path, FILL_LOG_PATH)
    trade_path = Path(trade_log_path) if trade_log_path is not None else resolve_trade_log_path(kind="trade_log")
    updates_path = Path(trade_updates_path) if trade_updates_path is not None else resolve_trade_log_path(kind="trade_updates")

    fill_rows = _iter_jsonl(fill_path)
    trade_rows = _iter_jsonl(trade_path)
    update_rows = _iter_jsonl(updates_path)

    context_by_trade: dict[str, dict[str, Any]] = {}
    for row in trade_rows + update_rows:
        trade_id = _trade_id(row)
        if not trade_id:
            continue
        context = context_by_trade.setdefault(trade_id, {})
        _merge_missing(context, _base_context(row))
        nested_fill = _fill_quality_payload(row)
        if nested_fill:
            _merge_missing(context, _base_context(nested_fill))
            _merge_missing(context, nested_fill)

    calibration_rows: list[dict[str, Any]] = []
    seen_fill_sources: set[str] = set()

    for index, row in enumerate(fill_rows, start=1):
        trade_id = _trade_id(row) or f"fill_quality:{index}"
        payload: dict[str, Any] = {}
        if trade_id in context_by_trade:
            _merge_missing(payload, context_by_trade[trade_id])
        _merge_missing(payload, _base_context(row))
        _merge_missing(payload, row)
        payload["trade_id"] = trade_id
        payload["depth_best"] = _depth_best(payload)
        calibration_rows.append(payload)
        seen_fill_sources.add(trade_id)

    for row in update_rows:
        nested_fill = _fill_quality_payload(row)
        if not nested_fill:
            continue
        trade_id = _trade_id(row) or _trade_id(nested_fill)
        if trade_id and trade_id in seen_fill_sources:
            continue
        payload: dict[str, Any] = {}
        if trade_id and trade_id in context_by_trade:
            _merge_missing(payload, context_by_trade[trade_id])
        _merge_missing(payload, _base_context(row))
        _merge_missing(payload, _base_context(nested_fill))
        _merge_missing(payload, nested_fill)
        payload["trade_id"] = trade_id or f"trade_update_fill:{len(calibration_rows) + 1}"
        payload["depth_best"] = _depth_best(payload)
        calibration_rows.append(payload)
        if trade_id:
            seen_fill_sources.add(trade_id)

    calibration_rows.sort(
        key=lambda row: (
            str(row.get("symbol") or "UNKNOWN"),
            int(_coerce_epoch_ms(row.get("timestamp_epoch_ms")) or 0),
            str(row.get("trade_id") or ""),
        )
    )
    return calibration_rows


def build_fill_quality_calibration_report(
    *,
    fill_quality_path: Path | None = None,
    trade_log_path: Path | None = None,
    trade_updates_path: Path | None = None,
    execution_performance_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    fill_path = _path_or_default(fill_quality_path, FILL_LOG_PATH)
    trade_path = Path(trade_log_path) if trade_log_path is not None else resolve_trade_log_path(kind="trade_log")
    updates_path = Path(trade_updates_path) if trade_updates_path is not None else resolve_trade_log_path(kind="trade_updates")
    perf_path = Path(execution_performance_path) if execution_performance_path is not None else Path(
        str(getattr(cfg, "EXEC_PERF_LOG_PATH", logs_dir() / "execution_performance.jsonl"))
    )

    calibration_rows = load_fill_quality_calibration_rows(
        fill_quality_path=fill_path,
        trade_log_path=trade_path,
        trade_updates_path=updates_path,
    )
    execution_perf_rows = _iter_jsonl(perf_path)
    perf_hints = _execution_perf_hints(execution_perf_rows)

    profiles = build_fill_quality_profiles(calibration_rows)
    profiles, matched_profiles = _apply_execution_performance_hints(profiles, perf_hints)

    notes: list[str] = []
    missing_optional = [
        name
        for name, path in (
            ("trade_log", trade_path),
            ("trade_updates", updates_path),
            ("execution_performance", perf_path),
        )
        if not Path(path).exists()
    ]
    if missing_optional:
        notes.append("missing_optional_artifacts:" + ",".join(sorted(missing_optional)))
    if not calibration_rows:
        notes.append("no_fill_quality_rows")
    if calibration_rows and not any(_safe_float(row.get("depth_best")) is not None for row in calibration_rows):
        notes.append("missing_depth_context_defaulted_to_volume_spread")
    if execution_perf_rows and matched_profiles == 0:
        notes.append("execution_performance_unmatched_to_symbol_profiles")

    report = {
        "fill_quality_log_rows": int(len(_iter_jsonl(fill_path))),
        "trade_log_rows": int(len(_iter_jsonl(trade_path))),
        "trade_update_rows": int(len(_iter_jsonl(updates_path))),
        "execution_performance_rows": int(len(execution_perf_rows)),
        "calibration_row_count": int(len(calibration_rows)),
        "profile_count": int(len(profiles)),
        "matched_execution_performance_profiles": int(matched_profiles),
        "profiles": {
            "columns": list(PROFILE_COLUMNS),
            "rows": profile_rows(profiles),
        },
        "notes": notes,
    }
    _write_report(output_path, report)
    return report

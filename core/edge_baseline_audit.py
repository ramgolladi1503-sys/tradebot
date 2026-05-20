from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import statistics
from pathlib import Path
from typing import Any, Iterable

from core.events import write_json_atomic
from core.offline_family_learning import family_outcome_records_path, load_family_outcome_records
from core.paths import ensure_dir, reports_dir

_REPORT_VERSION = 1
_SCORE_BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.0, 0.25, "0.00-0.25"),
    (0.25, 0.50, "0.25-0.50"),
    (0.50, 0.75, "0.50-0.75"),
    (0.75, 1.0000001, "0.75-1.00"),
)
_TERMINAL_STATUSES = {
    "executed",
    "rejected-saved-loss",
    "rejected-missed-win",
    "expired-no-move",
    "stopped",
    "target-hit",
    "timed-exit",
}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        number = float(value)
    except Exception:
        return None
    if number != number:  # NaN guard.
        return None
    return number


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _slug(value: Any, *, default: str = "unknown") -> str:
    text = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    return text or default


def _direction(record: dict[str, Any]) -> str:
    raw = (
        record.get("direction_family")
        or record.get("direction")
        or record.get("side")
        or record.get("signal_direction")
        or "unknown"
    )
    text = _slug(raw)
    if text in {"buy-call", "call", "ce", "bull", "bullish", "long-ce", "up"}:
        return "bullish"
    if text in {"buy-put", "put", "pe", "bear", "bearish", "long-pe", "down"}:
        return "bearish"
    return text


def _strategy_family(record: dict[str, Any]) -> str:
    return _slug(
        record.get("strategy_family")
        or record.get("family")
        or record.get("strategy")
        or record.get("strategy_name")
    )


def _regime(record: dict[str, Any]) -> str:
    return _slug(record.get("regime") or record.get("market_regime") or record.get("regime_day"))


def _normalized_score(record: dict[str, Any]) -> float | None:
    for key in ("final_score", "priority_score", "score", "confidence", "signal_score"):
        score = _safe_float(record.get(key))
        if score is None:
            continue
        if score > 1.0 and score <= 100.0:
            score = score / 100.0
        if score < 0.0 or score > 1.0:
            return None
        return score
    return None


def _score_bucket(score: float | None) -> str:
    if score is None:
        return "unknown"
    for lower, upper, label in _SCORE_BUCKETS:
        if lower <= score < upper:
            return label
    return "unknown"


def _realized_r(record: dict[str, Any]) -> float | None:
    return _safe_float(
        record.get("realized_r_multiple")
        if record.get("realized_r_multiple") is not None
        else record.get("r_multiple")
    )


def _raw_pnl(record: dict[str, Any]) -> float | None:
    for key in ("simulated_pnl", "realized_pnl", "pnl"):
        value = _safe_float(record.get(key))
        if value is not None:
            return value
    return None


def _slippage_cost(record: dict[str, Any]) -> float:
    for key in ("slippage_cost", "realized_slippage", "estimated_slippage", "slippage"):
        value = _safe_float(record.get(key))
        if value is not None:
            return abs(value)
    return 0.0


def _slippage_adjusted_pnl(record: dict[str, Any]) -> float | None:
    explicit = _safe_float(record.get("slippage_adjusted_pnl"))
    if explicit is not None:
        return explicit
    pnl = _raw_pnl(record)
    if pnl is None:
        return None
    return pnl - _slippage_cost(record)


def _terminal_status(record: dict[str, Any]) -> str:
    explicit = _slug(record.get("terminal_status") or record.get("candidate_terminal_status"), default="")
    if explicit:
        return explicit

    exit_reason = _slug(record.get("exit_reason"), default="")
    simulation_status = _slug(record.get("simulation_status") or record.get("status"), default="")

    if _safe_bool(record.get("rejection_saved_loss")):
        return "rejected-saved-loss"
    if _safe_bool(record.get("rejection_missed_win")):
        return "rejected-missed-win"
    if exit_reason in {"target-hit", "target", "profit-target"}:
        return "target-hit"
    if exit_reason in {"stop-hit", "stopped", "stoploss-hit", "sl-hit"}:
        return "stopped"
    if exit_reason in {"timed-exit", "time-exit", "time-stop"}:
        return "timed-exit"
    if exit_reason in {"expired-no-move", "no-move", "expired"}:
        return "expired-no-move"
    if simulation_status in {"executed", "sim-executed", "filled", "sim-partial-fill"}:
        return "executed"
    if simulation_status in {"expired-no-move", "expired"}:
        return "expired-no-move"
    return "unknown"


def _is_win(record: dict[str, Any], terminal_status: str) -> bool:
    r_value = _realized_r(record)
    if r_value is not None:
        return r_value > 0.0
    adjusted_pnl = _slippage_adjusted_pnl(record)
    if adjusted_pnl is not None:
        return adjusted_pnl > 0.0
    if _safe_bool(record.get("would_have_worked")):
        return True
    return terminal_status == "target-hit"


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(statistics.median(values)), 6)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(sum(values) / len(values)), 6)


def _max_drawdown(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        equity += float(pnl)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return round(float(max_dd), 6)


def _sort_key(record: dict[str, Any]) -> str:
    return str(record.get("timestamp") or record.get("ts") or "")


def normalize_edge_record(record: dict[str, Any]) -> dict[str, Any]:
    raw = dict(record or {})
    score = _normalized_score(raw)
    terminal_status = _terminal_status(raw)
    adjusted_pnl = _slippage_adjusted_pnl(raw)
    r_value = _realized_r(raw)
    return {
        "timestamp": str(raw.get("timestamp") or raw.get("ts") or ""),
        "strategy_family": _strategy_family(raw),
        "regime": _regime(raw),
        "direction": _direction(raw),
        "score": score,
        "score_bucket": _score_bucket(score),
        "terminal_status": terminal_status,
        "terminal_status_valid": terminal_status in _TERMINAL_STATUSES,
        "realized_r_multiple": r_value,
        "slippage_adjusted_pnl": adjusted_pnl,
        "is_win": _is_win(raw, terminal_status),
    }


def _summarize_bucket(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=_sort_key)
    r_values = [float(row["realized_r_multiple"]) for row in ordered if row.get("realized_r_multiple") is not None]
    pnl_values = [float(row["slippage_adjusted_pnl"]) for row in ordered if row.get("slippage_adjusted_pnl") is not None]
    sample_count = len(ordered)
    wins = sum(1 for row in ordered if bool(row.get("is_win")))
    return {
        "sample_count": int(sample_count),
        "win_rate": round(float(wins / sample_count), 6) if sample_count else 0.0,
        "average_r": _average(r_values),
        "median_r": _median(r_values),
        "r_sample_count": len(r_values),
        "max_drawdown": _max_drawdown(pnl_values),
        "slippage_adjusted_pnl": round(float(sum(pnl_values)), 6),
        "pnl_sample_count": len(pnl_values),
        "terminal_status_counts": dict(sorted(Counter(row["terminal_status"] for row in ordered).items())),
    }


def _bucket_validation(normalized: list[dict[str, Any]]) -> dict[str, Any]:
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        by_bucket[str(row.get("score_bucket") or "unknown")].append(row)

    buckets = {bucket: _summarize_bucket(rows) for bucket, rows in sorted(by_bucket.items())}
    high = buckets.get("0.75-1.00")
    mid = buckets.get("0.50-0.75")
    high_avg_r = high.get("average_r") if high else None
    mid_avg_r = mid.get("average_r") if mid else None
    high_win_rate = high.get("win_rate") if high else None
    mid_win_rate = mid.get("win_rate") if mid else None
    high_pnl = high.get("slippage_adjusted_pnl") if high else None
    mid_pnl = mid.get("slippage_adjusted_pnl") if mid else None

    comparable = bool(high and mid and high.get("sample_count", 0) > 0 and mid.get("sample_count", 0) > 0)
    avg_r_outperforms = None
    win_rate_outperforms = None
    pnl_outperforms = None
    if comparable and high_avg_r is not None and mid_avg_r is not None:
        avg_r_outperforms = bool(float(high_avg_r) > float(mid_avg_r))
    if comparable and high_win_rate is not None and mid_win_rate is not None:
        win_rate_outperforms = bool(float(high_win_rate) > float(mid_win_rate))
    if comparable and high_pnl is not None and mid_pnl is not None:
        pnl_outperforms = bool(float(high_pnl) > float(mid_pnl))

    return {
        "buckets": buckets,
        "comparison": {
            "high_bucket": "0.75-1.00",
            "mid_bucket": "0.50-0.75",
            "comparable": comparable,
            "high_average_r": high_avg_r,
            "mid_average_r": mid_avg_r,
            "high_win_rate": high_win_rate,
            "mid_win_rate": mid_win_rate,
            "high_slippage_adjusted_pnl": high_pnl,
            "mid_slippage_adjusted_pnl": mid_pnl,
            "average_r_outperforms_mid": avg_r_outperforms,
            "win_rate_outperforms_mid": win_rate_outperforms,
            "slippage_adjusted_pnl_outperforms_mid": pnl_outperforms,
            "scoring_predictive_on_available_data": bool(avg_r_outperforms and win_rate_outperforms and pnl_outperforms)
            if comparable
            else None,
        },
    }


def build_edge_baseline_report(
    records: Iterable[dict[str, Any]] | None = None,
    *,
    records_path: str | Path | None = None,
    strategy_family_filter: str | None = None,
) -> dict[str, Any]:
    raw_records = list(records) if records is not None else load_family_outcome_records(records_path or family_outcome_records_path())
    normalized = [normalize_edge_record(dict(row or {})) for row in raw_records]
    filter_value = _slug(strategy_family_filter, default="") if strategy_family_filter else ""
    if filter_value:
        normalized = [row for row in normalized if row.get("strategy_family") == filter_value]

    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        grouped[
            (
                str(row.get("strategy_family") or "unknown"),
                str(row.get("regime") or "unknown"),
                str(row.get("direction") or "unknown"),
                str(row.get("score_bucket") or "unknown"),
            )
        ].append(row)

    groups = []
    for (strategy_family, regime, direction, score_bucket), rows in sorted(grouped.items()):
        groups.append(
            {
                "strategy_family": strategy_family,
                "regime": regime,
                "direction": direction,
                "score_bucket": score_bucket,
                **_summarize_bucket(rows),
            }
        )

    terminal_counts = Counter(row["terminal_status"] for row in normalized)
    invalid_status_rows = [row for row in normalized if not bool(row.get("terminal_status_valid"))]
    source_path = str(Path(records_path).expanduser()) if records_path is not None else str(family_outcome_records_path())
    return {
        "version": _REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "records_path": source_path,
            "source_of_truth": "paper_outcome_journal",
            "read_only": True,
        },
        "filters": {
            "strategy_family": filter_value or None,
        },
        "journal_integrity": {
            "total_records": len(raw_records),
            "analyzed_records": len(normalized),
            "valid_terminal_status_records": len(normalized) - len(invalid_status_rows),
            "invalid_terminal_status_records": len(invalid_status_rows),
            "allowed_terminal_statuses": sorted(_TERMINAL_STATUSES),
            "terminal_status_counts": dict(sorted(terminal_counts.items())),
        },
        "grouping": "strategy_family x regime x direction x score_bucket",
        "groups": groups,
        "score_bucket_validation": _bucket_validation(normalized),
    }


def edge_baseline_report_path() -> Path:
    return ensure_dir(reports_dir()) / "edge_baseline_audit.json"


def save_edge_baseline_report(report: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path is not None else edge_baseline_report_path()
    return write_json_atomic(target, json.loads(json.dumps(dict(report or {}), ensure_ascii=True, default=str)))

"""Read-only ranking and opportunity diagnostics.

This module inspects emitted suggestion/candidate rows and reports whether the
current output looks like a ranked opportunity view or merely a filtered output
viewer. It does not change ranking formulas, execution gates, broker behavior,
depth subscriptions, or trade tuning.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any, Iterable

from core.paths import logs_dir as default_logs_dir

DEFAULT_SUGGESTIONS_JSONL = "suggestions.jsonl"

CONFIDENCE_FIELDS = (
    "confidence_raw",
    "raw_confidence",
    "confidence",
    "model_confidence",
    "signal_confidence",
)

RANK_FIELDS = (
    "rank",
    "opportunity_rank",
    "rank_position",
    "priority_rank",
    "display_rank",
)

OPPORTUNITY_SCORE_FIELDS = (
    "opportunity_score",
    "opportunity_score_raw",
    "edge_score",
    "alpha_score",
    "priority_score",
)

SIDE_FIELDS = (
    "side",
    "action",
    "direction",
    "order_side",
    "transaction_type",
    "signal_side",
    "trade_side",
)

STATUS_FIELDS = (
    "execution_status",
    "candidate_status",
    "status",
    "permission",
    "decision",
)

FALLBACK_SOURCE_FIELDS = (
    "source",
    "quote_source",
    "price_source",
    "ltp_source",
    "resolution_source",
    "data_source",
    "contract_source",
)

FALLBACK_FLAG_FIELDS = (
    "fallback",
    "fallback_used",
    "is_fallback",
    "recovered_fallback",
    "used_fallback",
)

BLOCKER_FIELDS = (
    "primary_blocker",
    "blocker",
    "block_reason",
    "status_reason",
    "execution_blocker",
    "execution_blockers",
    "blockers",
    "block_reasons",
    "reasons",
)

FLAT_CONFIDENCE_STD_THRESHOLD = 0.05
FLAT_CONFIDENCE_RANGE_THRESHOLD = 0.15
BUY_ONLY_RATIO_THRESHOLD = 0.95


def _resolve_logs_dir(log_root: str | Path | None = None) -> Path:
    if log_root is None:
        return default_logs_dir()
    return Path(log_root).expanduser()


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "ok"}


def _first_present(row: dict[str, Any], fields: Iterable[str]) -> tuple[str | None, Any]:
    for field in fields:
        if field in row and row.get(field) not in (None, ""):
            return field, row.get(field)
    return None, None


def _field_present(rows: list[dict[str, Any]], fields: Iterable[str]) -> bool:
    return any(_first_present(row, fields)[0] is not None for row in rows)


def _load_jsonl(path: Path, *, tail: int | None = None) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    if tail is not None:
        lines = lines[-max(1, int(tail)) :]
    rows: list[dict[str, Any]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    try:
        item = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []
    if isinstance(item, list):
        return [row for row in item if isinstance(row, dict)]
    if isinstance(item, dict):
        for key in ("rows", "suggestions", "candidates", "data"):
            value = item.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [item]
    return []


def _load_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def load_candidate_rows(
    *,
    input_path: str | Path | None = None,
    logs_dir: str | Path | None = None,
    tail: int | None = 500,
) -> tuple[list[dict[str, Any]], str]:
    """Load candidate/suggestion rows from a file or default runtime logs."""

    path = Path(input_path).expanduser() if input_path is not None else _resolve_logs_dir(logs_dir) / DEFAULT_SUGGESTIONS_JSONL
    suffix = path.suffix.lower()
    if suffix == ".csv":
        rows = _load_csv(path)
    elif suffix == ".json":
        rows = _load_json(path)
    else:
        rows = _load_jsonl(path, tail=tail)
    return rows, str(path)


def _confidence_values(rows: list[dict[str, Any]]) -> tuple[list[float], str | None]:
    values: list[float] = []
    used_field: str | None = None
    for row in rows:
        field, value = _first_present(row, CONFIDENCE_FIELDS)
        if field is None:
            continue
        number = _safe_float(value)
        if number is None:
            continue
        if used_field is None:
            used_field = field
        values.append(number)
    return values, used_field


def _summary_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "max": None, "mean": None, "std": None}
    return {
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
    }


def _side_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        _, value = _first_present(row, SIDE_FIELDS)
        text = str(value or "UNKNOWN").strip().upper() or "UNKNOWN"
        counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        _, value = _first_present(row, STATUS_FIELDS)
        text = str(value or "UNKNOWN").strip().upper() or "UNKNOWN"
        counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _contains_fallback(value: Any) -> bool:
    return "fallback" in str(value or "").strip().lower()


def _fallback_source_counts(rows: list[dict[str, Any]]) -> tuple[dict[str, int], int]:
    counts: dict[str, int] = {}
    recovered_count = 0
    for row in rows:
        row_is_recovered = False
        sources: list[str] = []
        for field in FALLBACK_SOURCE_FIELDS:
            if field in row and row.get(field) not in (None, ""):
                text = str(row.get(field)).strip()
                sources.append(text)
                if _contains_fallback(text):
                    row_is_recovered = True
        for field in FALLBACK_FLAG_FIELDS:
            if field not in row:
                continue
            value = row.get(field)
            if _truthy(value) or _contains_fallback(value) or field == "recovered_fallback":
                row_is_recovered = True
                sources.append(field if isinstance(value, bool) else str(value or field).strip())
        if row_is_recovered:
            recovered_count += 1
            if not sources:
                sources.append("fallback_detected")
        for source in sources:
            if not source:
                continue
            counts[source] = counts.get(source, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))), recovered_count


def _blocker_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for field in BLOCKER_FIELDS:
            if field not in row:
                continue
            value = row.get(field)
            items = value if isinstance(value, list) else [value]
            for item in items:
                text = str(item or "").strip()
                if not text or text.lower() in {"none", "nan", "null"}:
                    continue
                counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _count_matching_status(statuses: dict[str, int], needles: tuple[str, ...]) -> int:
    total = 0
    for key, count in statuses.items():
        upper = key.upper()
        if any(needle in upper for needle in needles):
            total += count
    return total


def _score_sequence(rows: list[dict[str, Any]]) -> list[float]:
    scores: list[float] = []
    for row in rows:
        _, value = _first_present(row, OPPORTUNITY_SCORE_FIELDS)
        number = _safe_float(value)
        if number is not None:
            scores.append(number)
    return scores


def _is_ranked_opportunity_view(rows: list[dict[str, Any]], rank_present: bool, score_present: bool) -> bool | None:
    if not rows:
        return None
    if rank_present:
        return True
    if score_present:
        scores = _score_sequence(rows)
        if len(scores) >= 2:
            descending = all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))
            ascending = all(scores[i] <= scores[i + 1] for i in range(len(scores) - 1))
            return descending or ascending
        return None
    return False


def build_opportunity_diagnostics(rows: list[dict[str, Any]], *, source_path: str | None = None) -> dict[str, Any]:
    """Build a read-only opportunity/ranking diagnostic report from rows."""

    confidence_values, confidence_field = _confidence_values(rows)
    confidence_stats = _summary_stats(confidence_values)
    confidence_min = confidence_stats["min"]
    confidence_max = confidence_stats["max"]
    confidence_std = confidence_stats["std"]
    confidence_range = None if confidence_min is None or confidence_max is None else confidence_max - confidence_min

    flat_confidence_detected = False
    if len(confidence_values) >= 3 and confidence_std is not None and confidence_range is not None:
        flat_confidence_detected = (
            confidence_std <= FLAT_CONFIDENCE_STD_THRESHOLD
            or confidence_range <= FLAT_CONFIDENCE_RANGE_THRESHOLD
        )

    side_counts = _side_counts(rows)
    row_count = len(rows)
    buy_count = side_counts.get("BUY", 0)
    sell_count = side_counts.get("SELL", 0)
    buy_side_ratio = buy_count / row_count if row_count else 0.0
    sell_side_ratio = sell_count / row_count if row_count else 0.0

    fallback_source_counts, recovered_fallback_count = _fallback_source_counts(rows)
    statuses = _status_counts(rows)
    top_blocker_counts = _blocker_counts(rows)
    rank_field_present = _field_present(rows, RANK_FIELDS)
    opportunity_score_present = _field_present(rows, OPPORTUNITY_SCORE_FIELDS)
    ui_is_ranked = _is_ranked_opportunity_view(rows, rank_field_present, opportunity_score_present)

    warnings: list[str] = []
    if row_count == 0:
        warnings.append("no_candidate_rows_visible")
    if confidence_field is None:
        warnings.append("confidence_field_missing")
    if flat_confidence_detected:
        warnings.append("flat_confidence_distribution")
    if row_count and buy_side_ratio >= BUY_ONLY_RATIO_THRESHOLD and sell_count == 0:
        warnings.append("buy_only_or_buy_dominant_output")
    if recovered_fallback_count:
        warnings.append("fallback_rows_visible")
    if not rank_field_present:
        warnings.append("rank_field_missing")
    if not opportunity_score_present:
        warnings.append("opportunity_score_missing")
    if ui_is_ranked is False:
        warnings.append("ui_appears_filtered_output_view_not_ranked_opportunity_view")

    return {
        "schema_version": 1,
        "generated_epoch": time.time(),
        "read_only": True,
        "is_order_action": False,
        "source_path": source_path,
        "row_count": row_count,
        "confidence_field": confidence_field,
        "confidence_raw_min": confidence_stats["min"],
        "confidence_raw_max": confidence_stats["max"],
        "confidence_raw_mean": confidence_stats["mean"],
        "confidence_raw_std": confidence_stats["std"],
        "flat_confidence_detected": flat_confidence_detected,
        "side_counts": side_counts,
        "buy_side_ratio": buy_side_ratio,
        "sell_side_ratio": sell_side_ratio,
        "fallback_source_counts": fallback_source_counts,
        "recovered_fallback_count": recovered_fallback_count,
        "status_counts": statuses,
        "executable_count": _count_matching_status(statuses, ("EXECUTE", "EXECUTABLE")),
        "queue_only_count": _count_matching_status(statuses, ("QUEUE_ONLY", "QUEUE", "NEAR_EXECUTABLE")),
        "advisory_count": _count_matching_status(statuses, ("ADVISORY",)),
        "top_blocker_counts": top_blocker_counts,
        "rank_field_present": rank_field_present,
        "opportunity_score_present": opportunity_score_present,
        "ui_is_ranked_opportunity_view": ui_is_ranked,
        "warnings": warnings,
    }


def write_opportunity_diagnostics_report(
    *,
    input_path: str | Path | None = None,
    logs_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    tail: int | None = 500,
) -> Path:
    rows, source = load_candidate_rows(input_path=input_path, logs_dir=logs_dir, tail=tail)
    report = build_opportunity_diagnostics(rows, source_path=source)
    root = _resolve_logs_dir(logs_dir)
    out = Path(output_path).expanduser() if output_path is not None else root / "opportunity_diagnostics_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(out)
    return out


__all__ = [
    "build_opportunity_diagnostics",
    "load_candidate_rows",
    "write_opportunity_diagnostics_report",
]

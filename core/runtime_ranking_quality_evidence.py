from __future__ import annotations

import json
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from config import config as cfg
from core.candidate_row_classification import classify_candidate_row
from core.events import write_json_atomic
from core.paths import logs_dir, runtime_dir


RUNTIME_RANKING_QUALITY_SCHEMA_VERSION = 1
RUNTIME_RANKING_QUALITY_SOURCE = "runtime_ranking_quality_evidence_v1"
RUNTIME_RANKING_QUALITY_FILENAME = "ranking_quality_latest.json"


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        out = float(value)
        return None if out != out else out
    except Exception:
        return None


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _std(values: list[float]) -> float | None:
    if len(values) < 2:
        return 0.0 if values else None
    return statistics.pstdev(values)


def _range(values: list[float]) -> float | None:
    return (max(values) - min(values)) if values else None


def _pct_gap(top: float | None, second: float | None) -> float | None:
    if top is None or second is None:
        return None
    base = max(abs(top), 1e-9)
    return float((top - second) / base)


def _fallbackish(row: Mapping[str, Any]) -> bool:
    r = _as_mapping(row)
    if bool(r.get("synthetic_candidate")) or bool(r.get("forced_fallback_execution")):
        return True
    quote_source = str(r.get("quote_source") or "").strip().lower()
    if "fallback" in quote_source:
        return True
    sf = r.get("source_flags")
    return isinstance(sf, dict) and bool(sf.get("recovered_fallback"))


def _component_counts(row: Mapping[str, Any]) -> tuple[Counter[str], Counter[str]]:
    """Return (missing, defaulted) component counters from phase2_score_detail when present."""
    missing: Counter[str] = Counter()
    defaulted: Counter[str] = Counter()
    r = _as_mapping(row)
    detail = r.get("phase2_score_detail")
    if not isinstance(detail, dict):
        return missing, defaulted
    for k, v in detail.items():
        key = str(k)
        if not key:
            continue
        if v in (None, "", "None"):
            missing[key] += 1
        # Heuristic: explicit *_fallback_used flags in score detail count as defaulted.
        if key.endswith("_fallback_used") and bool(v):
            defaulted[key] += 1
    return missing, defaulted


def build_ranking_quality_evidence_payload(
    *,
    candidates: list[Mapping[str, Any]] | None,
    phase2_state: str | None,
    cycle_primary_reason: str | None,
    phase2_min_enter_score: float | None = None,
) -> dict[str, Any]:
    rows = [dict(r) for r in list(candidates or []) if isinstance(r, Mapping)]
    state = str(phase2_state or "").strip().upper() or None
    min_enter = float(
        phase2_min_enter_score
        if phase2_min_enter_score is not None
        else float(getattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.70) or 0.70)
    )

    row_class_counts: Counter[str] = Counter()
    score_by_class: dict[str, list[float]] = defaultdict(list)
    score_by_strategy: dict[str, list[float]] = defaultdict(list)
    score_by_direction: dict[str, list[float]] = defaultdict(list)

    fallback_scores: list[float] = []
    real_scores: list[float] = []
    confidence_raws: list[float] = []
    final_scores: list[float] = []
    missing_components: Counter[str] = Counter()
    defaulted_components: Counter[str] = Counter()

    buy_count = 0
    sell_count = 0
    ce_count = 0
    pe_count = 0
    fallback_count = 0

    for row in rows:
        cls = classify_candidate_row(row=row, phase2_state=state, cycle_primary_reason=cycle_primary_reason)
        row_class_counts[cls.row_class] += 1

        score = _safe_float(row.get("final_score") or row.get("score"))
        conf_raw = _safe_float(row.get("confidence_raw"))
        if conf_raw is not None:
            confidence_raws.append(float(conf_raw))
        if score is not None:
            final_scores.append(float(score))
            score_by_class[cls.row_class].append(float(score))
            strat = str(row.get("strategy") or row.get("strategy_id") or "").strip() or "unknown_strategy"
            score_by_strategy[strat].append(float(score))
            direction = str(row.get("side") or row.get("direction") or "").strip().upper() or "UNKNOWN"
            score_by_direction[direction].append(float(score))

            if _fallbackish(row):
                fallback_scores.append(float(score))
                fallback_count += 1
            else:
                real_scores.append(float(score))

        side = str(row.get("side") or "").strip().upper()
        if side == "BUY":
            buy_count += 1
        elif side == "SELL":
            sell_count += 1
        opt_type = str(row.get("option_type") or row.get("type") or "").strip().upper()
        if opt_type == "CE":
            ce_count += 1
        elif opt_type == "PE":
            pe_count += 1

        miss, dflt = _component_counts(row)
        missing_components.update(miss)
        defaulted_components.update(dflt)

    top_score = max(final_scores) if final_scores else None
    sorted_scores = sorted(final_scores, reverse=True)
    second_score = sorted_scores[1] if len(sorted_scores) > 1 else None
    top_gap = None if top_score is None or second_score is None else float(top_score - second_score)
    top_gap_pct = _pct_gap(top_score, second_score)
    gap_to_enter = None if top_score is None else float(min_enter - float(top_score))

    # Compression heuristic: for real (non-fallback) scores only.
    real_range = _range(real_scores) or 0.0
    real_std = _std(real_scores) or 0.0
    compression = bool(len(real_scores) >= 3 and real_range <= 0.02 and real_std <= 0.01)
    compression_reason = None
    if compression:
        compression_reason = f"real_score_range={real_range:.6f}, real_score_std={real_std:.6f}"

    # Sort-field correctness: check whether first row has max final_score if candidate list looks sorted.
    rank_sort_field = "final_score"
    top_row_score = _safe_float(rows[0].get("final_score") or rows[0].get("score")) if rows else None
    max_score_seen = top_score
    top_row_has_max = (top_row_score is not None and max_score_seen is not None and math.isclose(float(top_row_score), float(max_score_seen), rel_tol=0, abs_tol=1e-12))

    direction_bias_warning = None
    if buy_count > 0 and sell_count == 0:
        direction_bias_warning = "all_buy"
    elif sell_count > 0 and buy_count == 0:
        direction_bias_warning = "all_sell"

    payload = {
        "schema_version": RUNTIME_RANKING_QUALITY_SCHEMA_VERSION,
        "source": RUNTIME_RANKING_QUALITY_SOURCE,
        "phase2_state": state,
        "input_candidate_count": int(len(rows)),
        "ranked_candidate_count": int(len(rows)),
        "row_class_counts": dict(row_class_counts),
        "executable_count": int(row_class_counts.get("EXECUTABLE", 0)),
        "near_executable_count": int(row_class_counts.get("NEAR_EXECUTABLE", 0)),
        "advisory_count": int(row_class_counts.get("ADVISORY", 0)),
        "debug_rejected_count": int(row_class_counts.get("DEBUG_REJECTED", 0)),
        "fallback_row_count": int(fallback_count),
        "confidence_raw_min": min(confidence_raws) if confidence_raws else None,
        "confidence_raw_max": max(confidence_raws) if confidence_raws else None,
        "confidence_raw_mean": _mean(confidence_raws),
        "confidence_raw_std": _std(confidence_raws),
        "confidence_raw_range": _range(confidence_raws),
        "final_score_min": min(final_scores) if final_scores else None,
        "final_score_max": max(final_scores) if final_scores else None,
        "final_score_mean": _mean(final_scores),
        "final_score_std": _std(final_scores),
        "final_score_range": _range(final_scores),
        "top_score": top_score,
        "second_score": second_score,
        "top_score_gap": top_gap,
        "top_score_gap_pct": top_gap_pct,
        "top_score_gap_to_enter_threshold": gap_to_enter,
        "phase2_min_enter_score": float(min_enter),
        "score_compression_detected": bool(compression),
        "score_compression_reason": compression_reason,
        "rank_sort_field": rank_sort_field,
        "top_row_score": top_row_score,
        "max_score_seen": max_score_seen,
        "top_row_has_max_score": bool(top_row_has_max),
        "ranking_order_valid": bool(top_row_has_max) if rows else True,
        "missing_component_counts": dict(missing_components),
        "defaulted_component_counts": dict(defaulted_components),
        "component_coverage_ratio": None if not rows else float(1.0 - (sum(missing_components.values()) / max(1.0, float(len(rows))))),
        "fallback_vs_real_score_distribution": {
            "real_count": int(len(real_scores)),
            "real_min": min(real_scores) if real_scores else None,
            "real_max": max(real_scores) if real_scores else None,
            "fallback_count": int(len(fallback_scores)),
            "fallback_min": min(fallback_scores) if fallback_scores else None,
            "fallback_max": max(fallback_scores) if fallback_scores else None,
        },
        "buy_count": int(buy_count),
        "sell_count": int(sell_count),
        "ce_count": int(ce_count),
        "pe_count": int(pe_count),
        "direction_bias_warning": direction_bias_warning,
        "score_distribution_by_row_class": {k: {"count": len(v), "min": min(v) if v else None, "max": max(v) if v else None} for k, v in score_by_class.items()},
        "score_distribution_by_strategy": {k: {"count": len(v), "min": min(v) if v else None, "max": max(v) if v else None} for k, v in score_by_strategy.items()},
        "score_distribution_by_direction": {k: {"count": len(v), "min": min(v) if v else None, "max": max(v) if v else None} for k, v in score_by_direction.items()},
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "generated_epoch": float(time.time()),
    }
    return json.loads(json.dumps(payload, ensure_ascii=True, default=str))


def write_ranking_quality_latest(
    *,
    payload: Mapping[str, Any],
    logs_path: Path | None = None,
    runtime_path: Path | None = None,
) -> tuple[Path, Path]:
    logs_target = Path(logs_path) if logs_path is not None else (logs_dir() / RUNTIME_RANKING_QUALITY_FILENAME)
    runtime_target = Path(runtime_path) if runtime_path is not None else (runtime_dir() / RUNTIME_RANKING_QUALITY_FILENAME)
    logs_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload) if isinstance(payload, Mapping) else {}
    write_json_atomic(logs_target, out)
    write_json_atomic(runtime_target, out)
    return logs_target, runtime_target


__all__ = ["RUNTIME_RANKING_QUALITY_FILENAME", "build_ranking_quality_evidence_payload", "write_ranking_quality_latest"]


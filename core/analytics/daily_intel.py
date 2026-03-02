from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config_delta import build_config_delta_proposal, write_config_delta
from .insights import (
    analyze_events,
    insight_feed_blocked_edge,
    insight_regime_flip,
    insight_target_sl_calibration,
    insight_top_bad_gates,
    insight_top_protective_gates,
)
from .markdown import render_daily_report_md


logger = logging.getLogger(__name__)


def _coerce_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        raise ValueError("day is required")
    return date.fromisoformat(text)


def _iter_days(day: date, window_days: int) -> list[date]:
    size = max(1, int(window_days))
    start = day - timedelta(days=size - 1)
    return [start + timedelta(days=i) for i in range(size)]


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except Exception as exc:
                    logger.warning("daily_intel_skip_bad_json path=%s line=%s err=%s", path, lineno, exc)
                    continue
                if not isinstance(payload, dict):
                    logger.warning("daily_intel_skip_non_object path=%s line=%s", path, lineno)
                    continue
                payload["_source_path"] = str(path)
                rows.append(payload)
    except Exception as exc:
        logger.warning("daily_intel_read_failed path=%s err=%s", path, exc)
    return rows


def _percentile(values: Sequence[float], pct: float) -> float | None:
    if not values:
        return None
    arr = sorted(float(v) for v in values)
    if len(arr) == 1:
        return float(arr[0])
    clamped = min(max(float(pct), 0.0), 1.0)
    pos = (len(arr) - 1) * clamped
    lo = int(pos)
    hi = min(lo + 1, len(arr) - 1)
    if lo == hi:
        return float(arr[lo])
    frac = pos - lo
    return float(arr[lo] + (arr[hi] - arr[lo]) * frac)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(dict(payload), ensure_ascii=True, indent=2, sort_keys=True)
    _atomic_write(path, encoded + "\n")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        return dict(payload)
    return None


def _extreme_movers_summary(extreme_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(extreme_payload, Mapping):
        return {"available": False}
    rows = list(extreme_payload.get("rows") or [])
    if not rows:
        return {"available": False}
    saw = sum(1 for row in rows if bool((row or {}).get("bot_saw")))
    rejected = sum(1 for row in rows if bool((row or {}).get("bot_rejected")))
    feed_related = 0
    reject_reasons: dict[str, int] = {}
    for row in rows:
        reasons = list((row or {}).get("reject_reasons") or [])
        for reason in reasons:
            key = str(reason)
            reject_reasons[key] = int(reject_reasons.get(key, 0)) + 1
            if key.lower().startswith("feed_state_"):
                feed_related += 1
        for state in list((row or {}).get("feed_state_at_reject") or []):
            text = str(state).upper()
            if text not in {"", "OK"}:
                feed_related += 1
    top_reasons = [name for name, _ in sorted(reject_reasons.items(), key=lambda item: (-item[1], item[0]))[:3]]
    return {
        "available": True,
        "movers_count": len(rows),
        "bot_saw_pct": (saw / len(rows)) if rows else 0.0,
        "bot_rejected_pct": (rejected / len(rows)) if rows else 0.0,
        "top_reject_reasons": top_reasons,
        "feed_related_reject_mentions": feed_related,
    }


def load_day_events(base_dir: Path, day: date, *, window_days: int = 1) -> list[dict[str, Any]]:
    base = Path(base_dir)
    target_day = _coerce_date(day)
    rows: list[dict[str, Any]] = []
    for day_item in _iter_days(target_day, window_days):
        day_key = day_item.isoformat()
        day_dir = base / day_key
        if day_dir.exists() and day_dir.is_dir():
            for path in sorted(day_dir.glob("*.jsonl")):
                rows.extend(_iter_jsonl(path))
        outcome_path = base / "outcomes" / f"{day_key}.jsonl"
        rows.extend(_iter_jsonl(outcome_path))
    return rows


def _confidence_suggestions(top_insights: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in top_insights:
        if not isinstance(item, Mapping):
            continue
        action = item.get("action")
        if not isinstance(action, Mapping):
            continue
        out.append(
            {
                "id": str(action.get("id") or f"insight_{int(item.get('rank') or 0)}"),
                "text": str(action.get("text") or "NO SUGGESTION (insufficient confidence)"),
                "sample_size": int(action.get("sample_size") or 0),
                "effect_size": float(action.get("effect_size") or 0.0),
                "sessions_count": int(action.get("sessions_count") or 0),
                "confidence_passed": bool(action.get("confidence_passed")),
            }
        )
    return out


def build_day_report(events: Sequence[Mapping[str, Any]], day: date) -> dict[str, Any]:
    target_day = _coerce_date(day)
    analysis = analyze_events(events)

    feed_insight = insight_feed_blocked_edge(events, analysis=analysis)
    bad_gate_insight = insight_top_bad_gates(events, analysis=analysis)
    protective_insight = insight_top_protective_gates(events, analysis=analysis)
    regime_insight = insight_regime_flip(events, analysis=analysis)
    calibration_insight = insight_target_sl_calibration(events, analysis=analysis)

    insight_rows = [
        bad_gate_insight,
        protective_insight,
        feed_insight,
        regime_insight,
        calibration_insight,
    ]
    top_insights: list[dict[str, Any]] = []
    for idx, item in enumerate(insight_rows, start=1):
        row = dict(item)
        row["rank"] = idx
        top_insights.append(row)

    rejected_with_outcomes = list(analysis.get("rejected_with_outcomes") or [])
    missed_total = int(analysis.get("missed_edge_count") or 0)
    missed_feed = int(analysis.get("missed_edge_due_to_feed") or 0)
    feed_related_share = (missed_feed / missed_total) if missed_total else 0.0

    gate_stats = list(analysis.get("gate_stats") or [])
    top_bad_gates = sorted(gate_stats, key=lambda row: (-int(row["hits"]), -int(row["count"])))[:3]
    top_protective_gates = sorted(gate_stats, key=lambda row: (-float(row["sl_rate"]), -int(row["count"])))[:3]

    quote_age_values = list(analysis.get("quote_age_values") or [])
    spread_values = list(analysis.get("spread_values") or [])

    metrics = {
        "feed": {
            "feed_block_rejects": int(analysis.get("feed_block_rejects") or 0),
            "rejects_by_feed_state": dict(analysis.get("rejects_by_feed_state") or {}),
            "rejects_by_feed_group": dict(analysis.get("rejects_by_feed_group") or {}),
            "missed_edge_due_to_feed": missed_feed,
            "missed_edge_due_to_other": int(analysis.get("missed_edge_due_to_other") or 0),
            "feed_related_share_of_missed_edge": feed_related_share,
        },
        "gates": {
            "rejects_by_reason_top10": dict(analysis.get("rejects_by_reason") or {}),
            "baseline_hit_rate": float(analysis.get("baseline_hit_rate") or 0.0),
            "baseline_sl_rate": float(analysis.get("baseline_sl_rate") or 0.0),
            "top_bad_gates": top_bad_gates,
            "top_protective_gates": top_protective_gates,
        },
        "outcomes": {
            "rejected_with_outcomes": len(rejected_with_outcomes),
            "missed_edge_count": missed_total,
            "saved_count": int(analysis.get("saved_count") or 0),
            "neutral_count": int(analysis.get("neutral_count") or 0),
            "outcome_replay_missing": bool(analysis.get("outcome_replay_missing")),
        },
        "regime": list(analysis.get("regime_stats") or []),
        "time_of_day": list(analysis.get("time_of_day_stats") or []),
        "target_sl_calibration": dict(analysis.get("target_sl_metrics") or {}),
        "quote_quality": {
            "quote_age_p50": _percentile(quote_age_values, 0.50),
            "quote_age_p95": _percentile(quote_age_values, 0.95),
            "spread_pct_p50": _percentile(spread_values, 0.50),
            "spread_pct_p95": _percentile(spread_values, 0.95),
        },
    }

    summary = {
        "total_rows_loaded": len(events),
        "total_trade_events": len(list(analysis.get("trade_events") or [])),
        "total_rejected_trades": len(list(analysis.get("rejected") or [])),
        "total_accepted_trades": len(list(analysis.get("accepted") or [])),
        "total_advisory_trades": len(list(analysis.get("advisory") or [])),
        "rejected_with_outcomes": len(rejected_with_outcomes),
        "total_feed_block_rejects": int(analysis.get("feed_block_rejects") or 0),
        "sessions_count": int(analysis.get("sessions_count") or 0),
        "sessions_by_day": dict(analysis.get("sessions_by_day") or {}),
    }

    report = {
        "day": target_day.isoformat(),
        "summary": summary,
        "top_insights": top_insights,
        "metrics": metrics,
        "suggestions": _confidence_suggestions(top_insights),
    }
    return report


def write_day_report(report: Mapping[str, Any], out_dir: Path) -> tuple[Path, Path]:
    day_key = str(report.get("day") or "").strip()
    if not day_key:
        raise ValueError("report.day is required")
    base = Path(out_dir) / day_key
    md_path = base / "daily_report.md"
    json_path = base / "daily_report.json"
    _atomic_write(md_path, render_daily_report_md(report))
    _atomic_write_json(json_path, report)
    return md_path, json_path


def write_day_outputs(report: Mapping[str, Any], out_dir: Path) -> tuple[Path, Path, Path, Path]:
    report_obj = dict(report)
    day_key = str(report_obj.get("day") or "").strip()
    ext_payload = _load_json(Path(out_dir) / day_key / "extreme_movers.json") if day_key else None
    metrics = dict(report_obj.get("metrics") or {})
    metrics["extreme_movers"] = _extreme_movers_summary(ext_payload)
    report_obj["metrics"] = metrics

    md_path, json_path = write_day_report(report_obj, out_dir)
    proposal = build_config_delta_proposal(report_obj)
    proposal_md_path, proposal_json_path = write_config_delta(proposal, out_dir)
    return md_path, json_path, proposal_md_path, proposal_json_path


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build offline Daily Intelligence report from runtime/analytics JSONL.")
    parser.add_argument("--day", required=True, help="Target day in YYYY-MM-DD.")
    parser.add_argument("--base", default="runtime/analytics", help="Base analytics directory (default: runtime/analytics).")
    parser.add_argument("--window-days", type=int, default=1, help="Number of trailing days to include (default: 1).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    target_day = _coerce_date(args.day)
    base = Path(args.base)
    rows = load_day_events(base, target_day, window_days=max(1, int(args.window_days)))
    report = build_day_report(rows, target_day)
    report["summary"]["window_days"] = max(1, int(args.window_days))
    md_path, json_path, proposal_md_path, proposal_json_path = write_day_outputs(report, base / "reports")
    print(
        json.dumps(
            {
                "day": target_day.isoformat(),
                "rows_loaded": len(rows),
                "window_days": max(1, int(args.window_days)),
                "daily_report_markdown_path": str(md_path),
                "daily_report_json_path": str(json_path),
                "config_delta_markdown_path": str(proposal_md_path),
                "config_delta_json_path": str(proposal_json_path),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

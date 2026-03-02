from __future__ import annotations

from typing import Any, Mapping, Sequence


def _text(value: Any) -> str:
    return str(value or "").strip()


def _fmt_pct(value: Any) -> str:
    try:
        val = float(value)
        return f"{val * 100.0:.1f}%"
    except Exception:
        return "n/a"


def _fmt_num(value: Any) -> str:
    try:
        val = float(value)
        if val.is_integer():
            return str(int(val))
        return f"{val:.3f}"
    except Exception:
        return "n/a"


def render_daily_report_md(report: Mapping[str, Any]) -> str:
    day = _text(report.get("day")) or "unknown-day"
    summary = dict(report.get("summary") or {})
    top_insights = list(report.get("top_insights") or [])
    metrics = dict(report.get("metrics") or {})
    suggestions = list(report.get("suggestions") or [])

    lines: list[str] = []
    lines.append(f"# Daily Intelligence Report - {day}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- sessions_count: {_fmt_num(summary.get('sessions_count'))}")
    lines.append(f"- total_trade_events: {_fmt_num(summary.get('total_trade_events'))}")
    lines.append(f"- total_rejected_trades: {_fmt_num(summary.get('total_rejected_trades'))}")
    lines.append(f"- total_accepted_trades: {_fmt_num(summary.get('total_accepted_trades'))}")
    lines.append(f"- total_advisory_trades: {_fmt_num(summary.get('total_advisory_trades'))}")
    lines.append(f"- rejected_with_outcomes: {_fmt_num(summary.get('rejected_with_outcomes'))}")
    lines.append("")

    lines.append("## Top 5 Insights")
    for item in top_insights:
        if not isinstance(item, Mapping):
            continue
        rank = int(item.get("rank") or 0)
        title = _text(item.get("title")) or "Untitled insight"
        what_happened = _text(item.get("what_happened")) or "n/a"
        action = item.get("action") if isinstance(item.get("action"), Mapping) else {}
        action_text = _text(action.get("text")) if isinstance(action, Mapping) else "n/a"
        lines.append(f"{rank}. **{title}**")
        lines.append(f"   - What happened: {what_happened}")
        lines.append(f"   - Action: {action_text}")
    if not top_insights:
        lines.append("1. Insufficient data to compute insights.")
    lines.append("")

    feed = dict(metrics.get("feed") or {})
    lines.append("## Feed")
    lines.append(f"- feed_block_rejects: {_fmt_num(feed.get('feed_block_rejects'))}")
    lines.append(f"- missed_edge_due_to_feed: {_fmt_num(feed.get('missed_edge_due_to_feed'))}")
    lines.append(f"- missed_edge_due_to_other_gates: {_fmt_num(feed.get('missed_edge_due_to_other'))}")
    lines.append(f"- feed_related_share_of_missed_edge: {_fmt_pct(feed.get('feed_related_share_of_missed_edge'))}")
    lines.append(f"- rejects_by_feed_state: {feed.get('rejects_by_feed_state') or {}}")
    lines.append(f"- rejects_by_feed_group: {feed.get('rejects_by_feed_group') or {}}")
    lines.append("")

    gates = dict(metrics.get("gates") or {})
    lines.append("## Gates")
    lines.append(f"- rejects_by_reason_top10: {gates.get('rejects_by_reason_top10') or {}}")
    lines.append(f"- baseline_hit_rate: {_fmt_pct(gates.get('baseline_hit_rate'))}")
    lines.append(f"- baseline_sl_rate: {_fmt_pct(gates.get('baseline_sl_rate'))}")
    lines.append(f"- top_bad_gates: {gates.get('top_bad_gates') or []}")
    lines.append(f"- top_protective_gates: {gates.get('top_protective_gates') or []}")
    lines.append("")

    regime = list(metrics.get("regime") or [])
    tod = list(metrics.get("time_of_day") or [])
    lines.append("## Regime + Time Of Day")
    lines.append(f"- regime: {regime}")
    lines.append(f"- time_of_day: {tod}")
    lines.append("")

    outcomes = dict(metrics.get("outcomes") or {})
    calibration = dict(metrics.get("target_sl_calibration") or {})
    lines.append("## Outcomes + Calibration")
    lines.append(f"- missed_edge_count: {_fmt_num(outcomes.get('missed_edge_count'))}")
    lines.append(f"- saved_count: {_fmt_num(outcomes.get('saved_count'))}")
    lines.append(f"- neutral_count: {_fmt_num(outcomes.get('neutral_count'))}")
    lines.append(f"- calibration: {calibration}")
    lines.append("")

    lines.append("## Suggestions (Confidence-Gated)")
    if suggestions:
        for idx, row in enumerate(suggestions, start=1):
            if not isinstance(row, Mapping):
                continue
            lines.append(
                f"{idx}. {_text(row.get('id'))}: {_text(row.get('text'))} "
                f"(sample_size={_fmt_num(row.get('sample_size'))}, "
                f"effect_size={_fmt_num(row.get('effect_size'))}, "
                f"sessions={_fmt_num(row.get('sessions_count'))}, "
                f"confidence_passed={bool(row.get('confidence_passed'))})"
            )
    else:
        lines.append("1. NO SUGGESTION (insufficient confidence)")
    lines.append("")

    return "\n".join(lines)

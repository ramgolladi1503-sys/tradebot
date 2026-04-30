from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import config as cfg
from core.paths import repo_root

from .feed_quality_correlation import build_feed_quality_correlation_report
from .gate_scorecard import build_gate_scorecard
from .missed_opportunity import analyze_missed_opportunity
from .shadow_portfolio import build_executable_shadow_portfolio_report
from .regime_analysis import build_regime_analysis
from .schema import TradeIntentEvent, TradeOutcome
from .target_sl_calibration import build_target_sl_calibration_report


IST = ZoneInfo("Asia/Kolkata")


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:  # NaN guard
            return None
        return out
    except Exception:
        return None


def _parse_date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = _norm_text(value)
    if not text:
        return datetime.now(tz=IST).date().isoformat()
    return datetime.fromisoformat(text).date().isoformat()


def _to_day_key(epoch_ms: int) -> str:
    return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST).date().isoformat()


def _report_dir(date_key: str) -> Path:
    base = _norm_text(getattr(cfg, "DAILY_REPORT_DIR", ""))
    if base:
        return Path(base) / date_key
    return repo_root() / "runtime" / "analytics" / "reports" / date_key


def _default_outcome_path(date_key: str) -> Path:
    base = _norm_text(getattr(cfg, "OUTCOME_REPLAY_DIR", ""))
    if base:
        return Path(base) / f"{date_key}.jsonl"
    return repo_root() / "runtime" / "analytics" / "outcomes" / f"{date_key}.jsonl"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write(
        path,
        json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, separators=(",", ":")),
    )


def _ensure_outcomes_available(date_key: str, *, attempt_replay: bool) -> dict:
    outcome_path = _default_outcome_path(date_key)
    status = {
        "path": str(outcome_path),
        "exists": bool(outcome_path.exists()),
        "attempted_replay": False,
        "replay_success": False,
        "warning": None,
    }
    if status["exists"]:
        return status

    if not attempt_replay:
        status["warning"] = f"Outcomes missing for {date_key}; replay skipped."
        return status

    status["attempted_replay"] = True
    try:
        cmd = [sys.executable, "-m", "core.analytics.outcome_replay", "--date", date_key]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=int(getattr(cfg, "DAILY_REPORT_OUTCOME_REPLAY_TIMEOUT_SEC", 180)),
        )
        if proc.returncode == 0 and outcome_path.exists():
            status["exists"] = True
            status["replay_success"] = True
        else:
            tail = ""
            stderr = _norm_text(proc.stderr)
            stdout = _norm_text(proc.stdout)
            if stderr:
                tail = stderr.splitlines()[-1]
            elif stdout:
                tail = stdout.splitlines()[-1]
            status["warning"] = (
                f"Outcome replay unavailable or failed (exit={proc.returncode}); outcomes still missing. {tail}".strip()
            )
    except Exception as exc:
        status["warning"] = f"Outcome replay unavailable or failed: {type(exc).__name__}: {exc}"

    return status


def _format_ts_ist(epoch_ms: int | None) -> str | None:
    if epoch_ms is None:
        return None
    try:
        dt = datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST)
        return dt.strftime("%Y-%m-%d %H:%M:%S IST")
    except Exception:
        return None


def _extract_examples(missed_payload: Mapping[str, Any], gate_name: str, reject_reason: str, *, limit: int = 2) -> list[dict]:
    rows = list(missed_payload.get("rows") or [])
    candidates = [
        row
        for row in rows
        if _norm_text(row.get("gate_name")) == gate_name and _norm_text(row.get("reject_reason")) == reject_reason
    ]

    label_rank = {"CLEAR_MISS": 0, "PARTIAL_EDGE": 1, "NO_EDGE": 2}

    def _sort_key(row: Mapping[str, Any]) -> tuple:
        label = _norm_text(row.get("label"))
        rank = label_rank.get(label, 3)
        mfe = _safe_float(row.get("mfe_points"))
        score = abs(float(mfe)) if mfe is not None else -1.0
        return (rank, -score, int(float(row.get("ts_epoch_ms") or 0)))

    candidates.sort(key=_sort_key)
    out: list[dict] = []
    for row in candidates[: max(int(limit), 0)]:
        ts_ms = int(float(row.get("ts_epoch_ms") or 0)) if row.get("ts_epoch_ms") is not None else None
        out.append(
            {
                "trade_key": row.get("trade_key"),
                "time": _format_ts_ist(ts_ms),
                "mfe_points": _safe_float(row.get("mfe_points")),
                "mae_points": _safe_float(row.get("mae_points")),
                "outcome": row.get("outcome"),
            }
        )
    return out


def _blocked_edge_section(gate_payload: Mapping[str, Any], missed_payload: Mapping[str, Any]) -> list[dict]:
    rows = list(gate_payload.get("by_gate_reject_reason") or [])
    negatives = [row for row in rows if _safe_float(row.get("net_edge_score")) is not None and float(row.get("net_edge_score")) < 0.0]
    negatives.sort(key=lambda row: (float(row.get("net_edge_score") or 0.0), -(int(row.get("blocked_count") or 0))))

    out: list[dict] = []
    for row in negatives[:3]:
        gate_name = _norm_text(row.get("gate_name")) or "unknown_gate"
        reject_reason = _norm_text(row.get("reject_reason")) or "unknown_reject"
        out.append(
            {
                "gate_name": gate_name,
                "reject_reason": reject_reason,
                "blocked_count": int(row.get("blocked_count") or 0),
                "blocked_would_win": int(row.get("blocked_would_win") or 0),
                "blocked_would_lose": int(row.get("blocked_would_lose") or 0),
                "blocked_neutral": int(row.get("blocked_neutral") or 0),
                "net_edge_score": float(row.get("net_edge_score") or 0.0),
                "examples": _extract_examples(missed_payload, gate_name, reject_reason, limit=2),
            }
        )
    return out


def _protective_section(gate_payload: Mapping[str, Any]) -> list[dict]:
    rows = list(gate_payload.get("gate_precision_recall") or [])
    eligible = [row for row in rows if int(row.get("blocked_count") or 0) > 0]
    eligible.sort(
        key=lambda row: (
            -(float(_safe_float(row.get("block_precision")) or 0.0)),
            -(int(row.get("blocked_count") or 0)),
        )
    )

    out: list[dict] = []
    for row in eligible[:3]:
        out.append(
            {
                "gate_name": _norm_text(row.get("gate_name")) or "unknown_gate",
                "blocked_count": int(row.get("blocked_count") or 0),
                "block_precision": _safe_float(row.get("block_precision")),
                "block_recall": _safe_float(row.get("block_recall")),
                "blocked_would_lose": int(row.get("blocked_would_lose") or 0),
                "blocked_would_win": int(row.get("blocked_would_win") or 0),
            }
        )
    return out


def _regime_notes_section(regime_payload: Mapping[str, Any]) -> list[dict]:
    rows = list(regime_payload.get("gate_net_edge_by_regime") or [])
    by_gate: dict[str, list[dict]] = {}
    for row in rows:
        gate = _norm_text(row.get("gate_name")) or "unknown_gate"
        if int(row.get("blocked_count") or 0) <= 0:
            continue
        by_gate.setdefault(gate, []).append(dict(row))

    notes: list[dict] = []
    for gate, items in by_gate.items():
        pos = [item for item in items if _safe_float(item.get("net_edge_score")) is not None and float(item.get("net_edge_score")) > 0.0]
        neg = [item for item in items if _safe_float(item.get("net_edge_score")) is not None and float(item.get("net_edge_score")) < 0.0]
        if not pos or not neg:
            continue
        max_pos = max(float(item.get("net_edge_score") or 0.0) for item in pos)
        min_neg = min(float(item.get("net_edge_score") or 0.0) for item in neg)
        notes.append(
            {
                "gate_name": gate,
                "positive_regimes": sorted({_norm_text(item.get("regime")) for item in pos if _norm_text(item.get("regime"))}),
                "negative_regimes": sorted({_norm_text(item.get("regime")) for item in neg if _norm_text(item.get("regime"))}),
                "flip_span": float(max_pos - min_neg),
                "max_positive_score": float(max_pos),
                "max_negative_score": float(min_neg),
            }
        )

    notes.sort(key=lambda row: (-float(row.get("flip_span") or 0.0), _norm_text(row.get("gate_name"))))
    return notes[:5]


def _target_sl_section(payload: Mapping[str, Any]) -> dict:
    target = payload.get("target_metrics") if isinstance(payload.get("target_metrics"), Mapping) else {}
    stop = payload.get("stop_metrics") if isinstance(payload.get("stop_metrics"), Mapping) else {}

    return {
        "target_samples": int(target.get("samples") or 0),
        "pct_mfe_ge_target": _safe_float(target.get("pct_mfe_ge_target")),
        "avg_left_on_table_points": _safe_float(target.get("avg_left_on_table_points")),
        "avg_target_points": _safe_float(target.get("avg_target_points")),
        "stop_samples": int(stop.get("samples") or 0),
        "pct_mae_ge_stop": _safe_float(stop.get("pct_mae_ge_stop")),
        "avg_too_tight_points": _safe_float(stop.get("avg_too_tight_points")),
        "avg_stop_points": _safe_float(stop.get("avg_stop_points")),
        "recommendation_method": _norm_text((payload.get("recommendations") or {}).get("method")) or None,
    }


def _feed_quality_section(payload: Mapping[str, Any]) -> dict:
    suggestions = payload.get("threshold_suggestions") if isinstance(payload.get("threshold_suggestions"), Mapping) else {}
    return {
        "quote_age_threshold": suggestions.get("quote_age_sec") if isinstance(suggestions.get("quote_age_sec"), Mapping) else None,
        "spread_threshold": suggestions.get("spread_pct") if isinstance(suggestions.get("spread_pct"), Mapping) else None,
        "feed_state_thresholds": list(suggestions.get("feed_state") or []),
        "correlations": dict(payload.get("correlations") or {}),
    }


def _executable_shadow_section(payload: Mapping[str, Any]) -> dict:
    counts = payload.get("counts") if isinstance(payload.get("counts"), Mapping) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    return {
        "scanned_events": int(counts.get("scanned_events") or 0),
        "eligible_events": int(counts.get("eligible_events") or 0),
        "simulated_trades": int(counts.get("simulated_trades") or 0),
        "skipped_events": int(counts.get("skipped_events") or 0),
        "wins": int(summary.get("wins") or 0),
        "losses": int(summary.get("losses") or 0),
        "total_pnl_value": _safe_float(summary.get("total_pnl_value")),
        "ending_equity": _safe_float(summary.get("ending_equity")),
        "max_drawdown_points": _safe_float(summary.get("max_drawdown_points")),
        "skip_reasons": dict(payload.get("skip_reasons") or {}),
    }


def _build_action_list(
    *,
    feed_section: Mapping[str, Any],
    target_section: Mapping[str, Any],
) -> list[dict]:
    actions: list[dict] = []

    quote_thr = feed_section.get("quote_age_threshold") if isinstance(feed_section.get("quote_age_threshold"), Mapping) else None
    if quote_thr:
        drop = _safe_float(quote_thr.get("drop"))
        n_low = int(quote_thr.get("samples_at_or_below") or 0)
        n_high = int(quote_thr.get("samples_above") or 0)
        thr = _safe_float(quote_thr.get("threshold"))
        if drop is not None and drop >= 0.15 and min(n_low, n_high) >= 10 and thr is not None:
            actions.append(
                {
                    "status": "suggested",
                    "confidence": "high",
                    "title": "Quote-age freshness",
                    "suggestion": f"Set LIVE_MAX_QUOTE_AGE_SEC to about {thr:.3f} (observed win-rate drop {drop:.2f} above threshold).",
                }
            )

    spread_thr = feed_section.get("spread_threshold") if isinstance(feed_section.get("spread_threshold"), Mapping) else None
    if spread_thr:
        drop = _safe_float(spread_thr.get("drop"))
        n_low = int(spread_thr.get("samples_at_or_below") or 0)
        n_high = int(spread_thr.get("samples_above") or 0)
        thr = _safe_float(spread_thr.get("threshold"))
        if drop is not None and drop >= 0.10 and min(n_low, n_high) >= 10 and thr is not None:
            actions.append(
                {
                    "status": "suggested",
                    "confidence": "high",
                    "title": "Spread quality",
                    "suggestion": f"Set LIVE_MAX_SPREAD_PCT near {thr:.4f} (win-rate drop {drop:.2f} when spread is wider).",
                }
            )

    target_samples = int(target_section.get("target_samples") or 0)
    pct_target = _safe_float(target_section.get("pct_mfe_ge_target"))
    left_on_table = _safe_float(target_section.get("avg_left_on_table_points"))
    avg_target = _safe_float(target_section.get("avg_target_points"))
    if target_samples >= 20 and pct_target is not None and left_on_table is not None:
        ratio = (left_on_table / avg_target) if avg_target and avg_target > 0 else None
        if pct_target >= 0.65 and left_on_table > 0 and (ratio is None or ratio >= 0.10):
            actions.append(
                {
                    "status": "suggested",
                    "confidence": "high",
                    "title": "Target sizing",
                    "suggestion": "Increase TARGET_RR_DEFAULT modestly (for example +0.1) and re-evaluate next session.",
                }
            )

    while len(actions) < 3:
        actions.append(
            {
                "status": "no_change",
                "confidence": "low",
                "title": "No change",
                "suggestion": "No high-confidence config change identified from today’s sample.",
            }
        )

    return actions[:3]


def _safe_builder_call(name: str, fn, *, warnings: list[str], **kwargs) -> dict:
    try:
        payload = fn(**kwargs)
        if isinstance(payload, Mapping):
            return dict(payload)
        warnings.append(f"{name}: builder returned non-dict payload")
        return {}
    except Exception as exc:
        warnings.append(f"{name}: build failed: {type(exc).__name__}: {exc}")
        return {}


def _compose_markdown(
    *,
    date_key: str,
    universe: Sequence[str],
    counts: Mapping[str, Any],
    blocked_edge: Sequence[Mapping[str, Any]],
    protective: Sequence[Mapping[str, Any]],
    regime_notes: Sequence[Mapping[str, Any]],
    target_sl: Mapping[str, Any],
    feed_quality: Mapping[str, Any],
    executable_shadow: Mapping[str, Any],
    action_list: Sequence[Mapping[str, Any]],
    warnings: Sequence[str],
) -> str:
    lines: list[str] = []
    lines.append(f"# Daily Intelligence Report - {date_key}")
    lines.append("")
    lines.append(f"Date: {date_key}")
    lines.append(f"Universe: {', '.join(universe) if universe else 'UNKNOWN'}")
    lines.append(
        "Counts: "
        f"events={int(counts.get('events') or 0)}, "
        f"matched_outcomes={int(counts.get('matched_outcomes') or 0)}, "
        f"rejected={int(counts.get('rejected') or 0)}"
    )
    lines.append("")

    lines.append("## Section 1: What blocked edge yesterday?")
    if blocked_edge:
        for row in blocked_edge:
            lines.append(
                "- "
                f"{_norm_text(row.get('gate_name'))} / {_norm_text(row.get('reject_reason'))} | "
                f"net_edge={float(row.get('net_edge_score') or 0.0):.3f} | "
                f"blocked={int(row.get('blocked_count') or 0)} | "
                f"win={int(row.get('blocked_would_win') or 0)} | lose={int(row.get('blocked_would_lose') or 0)}"
            )
            examples = list(row.get("examples") or [])
            if examples:
                for ex in examples:
                    lines.append(
                        "  "
                        f"- trade_key={_norm_text(ex.get('trade_key'))} | time={_norm_text(ex.get('time'))} | "
                        f"mfe={ex.get('mfe_points')} | mae={ex.get('mae_points')} | outcome={_norm_text(ex.get('outcome')) or 'unknown'}"
                    )
            else:
                lines.append("  - no representative rejects found")
    else:
        lines.append("- No net-negative gates found.")
    lines.append("")

    lines.append("## Section 2: What saved you?")
    if protective:
        for row in protective:
            lines.append(
                "- "
                f"{_norm_text(row.get('gate_name'))} | blocked={int(row.get('blocked_count') or 0)} | "
                f"block_precision={_safe_float(row.get('block_precision'))} | block_recall={_safe_float(row.get('block_recall'))}"
            )
    else:
        lines.append("- No protective gate signal available.")
    lines.append("")

    lines.append("## Section 3: Regime notes")
    if regime_notes:
        for row in regime_notes:
            lines.append(
                "- "
                f"{_norm_text(row.get('gate_name'))}: flipped sign across regimes | "
                f"positive={', '.join(row.get('positive_regimes') or []) or 'n/a'} | "
                f"negative={', '.join(row.get('negative_regimes') or []) or 'n/a'}"
            )
    else:
        lines.append("- No gate sign flips detected across regimes.")
    lines.append("")

    lines.append("## Section 4: Target/SL calibration")
    lines.append(
        "- "
        f"target_samples={int(target_sl.get('target_samples') or 0)}, "
        f"pct_mfe_ge_target={_safe_float(target_sl.get('pct_mfe_ge_target'))}, "
        f"avg_left_on_table_points={_safe_float(target_sl.get('avg_left_on_table_points'))}"
    )
    lines.append(
        "- "
        f"stop_samples={int(target_sl.get('stop_samples') or 0)}, "
        f"pct_mae_ge_stop={_safe_float(target_sl.get('pct_mae_ge_stop'))}, "
        f"avg_too_tight_points={_safe_float(target_sl.get('avg_too_tight_points'))}"
    )
    lines.append("")

    lines.append("## Section 5: Feed quality impact")
    qa = feed_quality.get("quote_age_threshold") if isinstance(feed_quality.get("quote_age_threshold"), Mapping) else None
    sp = feed_quality.get("spread_threshold") if isinstance(feed_quality.get("spread_threshold"), Mapping) else None
    if qa:
        lines.append(
            "- "
            f"quote_age threshold={_safe_float(qa.get('threshold'))}, drop={_safe_float(qa.get('drop'))}, "
            f"samples=({_norm_text(qa.get('samples_at_or_below'))},{_norm_text(qa.get('samples_above'))})"
        )
    else:
        lines.append("- quote_age: no strong threshold identified")
    if sp:
        lines.append(
            "- "
            f"spread threshold={_safe_float(sp.get('threshold'))}, drop={_safe_float(sp.get('drop'))}, "
            f"samples=({_norm_text(sp.get('samples_at_or_below'))},{_norm_text(sp.get('samples_above'))})"
        )
    else:
        lines.append("- spread: no strong threshold identified")
    lines.append("")

    lines.append("## Section 6: Executable shadow portfolio")
    lines.append(
        "- "
        f"scanned={int(executable_shadow.get('scanned_events') or 0)}, "
        f"eligible={int(executable_shadow.get('eligible_events') or 0)}, "
        f"simulated_trades={int(executable_shadow.get('simulated_trades') or 0)}, "
        f"skipped={int(executable_shadow.get('skipped_events') or 0)}"
    )
    lines.append(
        "- "
        f"wins={int(executable_shadow.get('wins') or 0)}, "
        f"losses={int(executable_shadow.get('losses') or 0)}, "
        f"total_pnl_value={_safe_float(executable_shadow.get('total_pnl_value'))}, "
        f"max_drawdown_points={_safe_float(executable_shadow.get('max_drawdown_points'))}"
    )
    lines.append(f"- skip_reasons={dict(executable_shadow.get('skip_reasons') or {})}")
    lines.append("")

    lines.append("## Action list")
    for idx, row in enumerate(list(action_list or [])[:3], start=1):
        lines.append(f"{idx}. [{_norm_text(row.get('status'))}] {_norm_text(row.get('suggestion'))}")
    lines.append("")

    if warnings:
        lines.append("## Warnings")
        for item in warnings:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_daily_intelligence_report(
    date: Any,
    *,
    events: Sequence[TradeIntentEvent | Mapping[str, Any]] | None = None,
    outcomes: Sequence[TradeOutcome | Mapping[str, Any]] | None = None,
    quote_rows: Sequence[Mapping[str, Any]] | None = None,
    attempt_outcome_replay: bool = True,
    output_dir: Path | None = None,
) -> dict:
    date_key = _parse_date_key(date)
    base_dir = Path(output_dir) if output_dir is not None else _report_dir(date_key)
    base_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []

    outcomes_status = _ensure_outcomes_available(date_key, attempt_replay=bool(attempt_outcome_replay))
    if _norm_text(outcomes_status.get("warning")):
        warnings.append(_norm_text(outcomes_status.get("warning")))

    gate_path = base_dir / "gate_scorecard.json"
    missed_path = base_dir / "missed_opportunity.json"
    regime_path = base_dir / "regime_analysis.json"
    tsl_path = base_dir / "target_sl_calibration.json"
    feed_path = base_dir / "feed_quality_correlation.json"
    executable_shadow_path = base_dir / "executable_shadow_portfolio.json"

    gate_payload = _safe_builder_call(
        "gate_scorecard",
        build_gate_scorecard,
        warnings=warnings,
        date=date_key,
        events=events,
        outcomes=outcomes,
        output_path=gate_path,
    )
    missed_payload = _safe_builder_call(
        "missed_opportunity",
        analyze_missed_opportunity,
        warnings=warnings,
        date=date_key,
        rejected_events=events,
        outcomes=outcomes,
        output_path=missed_path,
    )
    regime_payload = _safe_builder_call(
        "regime_analysis",
        build_regime_analysis,
        warnings=warnings,
        date=date_key,
        events=events,
        outcomes=outcomes,
        output_path=regime_path,
    )
    tsl_payload = _safe_builder_call(
        "target_sl_calibration",
        build_target_sl_calibration_report,
        warnings=warnings,
        date=date_key,
        events=events,
        outcomes=outcomes,
        output_path=tsl_path,
    )
    feed_payload = _safe_builder_call(
        "feed_quality_correlation",
        build_feed_quality_correlation_report,
        warnings=warnings,
        date=date_key,
        events=events,
        outcomes=outcomes,
        quote_rows=quote_rows,
        output_path=feed_path,
    )
    executable_shadow_payload = {}
    if bool(getattr(cfg, "DAILY_REPORT_INCLUDE_EXECUTABLE_SHADOW", True)) and bool(
        getattr(cfg, "EXECUTABLE_SHADOW_PORTFOLIO_ENABLE", True)
    ):
        executable_shadow_payload = _safe_builder_call(
            "executable_shadow_portfolio",
            build_executable_shadow_portfolio_report,
            warnings=warnings,
            date=date_key,
            output_path=executable_shadow_path,
        )

    blocked_edge = _blocked_edge_section(gate_payload, missed_payload)
    protective = _protective_section(gate_payload)
    regime_notes = _regime_notes_section(regime_payload)
    target_sl = _target_sl_section(tsl_payload)
    feed_quality = _feed_quality_section(feed_payload)
    executable_shadow = _executable_shadow_section(executable_shadow_payload)
    action_list = _build_action_list(feed_section=feed_quality, target_section=target_sl)

    symbols: set[str] = set()
    for payload in (missed_payload, feed_payload):
        for row in list(payload.get("rows") or []):
            sym = _norm_text(row.get("symbol")).upper()
            if sym:
                symbols.add(sym)
    if events is not None:
        for item in events:
            if isinstance(item, TradeIntentEvent):
                if _to_day_key(int(item.ts_epoch_ms)) == date_key:
                    sym = _norm_text(item.symbol).upper()
                    if sym:
                        symbols.add(sym)
            elif isinstance(item, Mapping):
                ts = item.get("ts_epoch_ms")
                if ts is None:
                    continue
                try:
                    if _to_day_key(int(float(ts))) != date_key:
                        continue
                except Exception:
                    continue
                sym = _norm_text(item.get("symbol")).upper()
                if sym:
                    symbols.add(sym)

    header_counts = {
        "events": int(gate_payload.get("total_events") or 0),
        "matched_outcomes": int(tsl_payload.get("matched_outcomes") or 0),
        "rejected": int(missed_payload.get("total_rejected") or 0),
    }

    markdown = _compose_markdown(
        date_key=date_key,
        universe=sorted(symbols),
        counts=header_counts,
        blocked_edge=blocked_edge,
        protective=protective,
        regime_notes=regime_notes,
        target_sl=target_sl,
        feed_quality=feed_quality,
        executable_shadow=executable_shadow,
        action_list=action_list,
        warnings=warnings,
    )

    md_path = base_dir / "daily_report.md"
    json_path = base_dir / "daily_report.json"

    json_payload = {
        "date": date_key,
        "header": {
            "universe": sorted(symbols),
            "counts": header_counts,
        },
        "outcomes_status": outcomes_status,
        "sections": {
            "blocked_edge": blocked_edge,
            "protective_gates": protective,
            "regime_notes": regime_notes,
            "target_sl_calibration": target_sl,
            "feed_quality_impact": feed_quality,
            "executable_shadow_portfolio": executable_shadow,
        },
        "action_list": action_list,
        "analytics_outputs": {
            "gate_scorecard": str(gate_path),
            "missed_opportunity": str(missed_path),
            "regime_analysis": str(regime_path),
            "target_sl_calibration": str(tsl_path),
            "feed_quality_correlation": str(feed_path),
            "executable_shadow_portfolio": str(executable_shadow_path),
        },
        "warnings": warnings,
    }

    _atomic_write(md_path, markdown)
    _atomic_write_json(json_path, json_payload)

    json_payload["daily_report_markdown_path"] = str(md_path)
    json_payload["daily_report_json_path"] = str(json_path)
    return json_payload


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a single Daily Intelligence Report from analytics modules.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD (exchange local day).")
    parser.add_argument("--output-dir", default=None, help="Optional output directory override.")
    parser.add_argument(
        "--skip-outcome-replay",
        action="store_true",
        help="Do not attempt to run outcome replay when outcomes are missing.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    out_dir = Path(args.output_dir) if args.output_dir else None
    payload = build_daily_intelligence_report(
        args.date,
        attempt_outcome_replay=not bool(args.skip_outcome_replay),
        output_dir=out_dir,
    )
    print(
        json.dumps(
            {
                "date": payload.get("date"),
                "header": payload.get("header"),
                "outcomes_status": payload.get("outcomes_status"),
                "warnings": payload.get("warnings"),
                "daily_report_markdown_path": payload.get("daily_report_markdown_path"),
                "daily_report_json_path": payload.get("daily_report_json_path"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

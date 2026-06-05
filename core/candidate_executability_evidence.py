from __future__ import annotations

import ast
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from core.events import write_json_atomic


CANDIDATE_EXECUTABILITY_EVIDENCE_SCHEMA_VERSION = 1
_CANDIDATE_EVENTS = {
    "TB_TOP_REAL_CANDIDATE",
    "TB_TOP_EXECUTABLE_CANDIDATE",
    "TB_TOP_ADVISORY_CANDIDATE",
    "TB_TOP_BLOCKED_CANDIDATE",
    "TB_TOP_SYNTH_CANDIDATE",
}
_SUPPLY_EVENTS = {
    "RAW_CANDIDATE_COUNT",
    "POST_SCAN_SURVIVOR_COUNT",
    "POST_REAL_FILTER_COUNT",
    "POST_EXECUTABLE_FILTER_COUNT",
    "TB_RANKED_COUNT_REAL",
    "TB_RANKED_COUNT_EXECUTABLE",
    "TB_RANKED_COUNT_ADVISORY",
    "TB_RANKED_COUNT_BLOCKED",
}
_FINAL_EMIT_EVENTS = {"FINAL_EMIT_ABORT", "FINAL_EMIT_ABORTED"}
_PHASE2_EVENTS = {
    "PHASE2_NO_VALID_CANDIDATES_AFTER_FILTERING",
    "PHASE2_NO_INPUT_CANDIDATES_FOR_PHASE2",
}
_TRADE_BUILDER_REJECT_EVENTS = {
    "TB_REJECT_SUMMARY",
    "OPTION_SCAN_REJECT_SUMMARY",
    "NO_CANDIDATE_PATH",
}
_FEED_RUNTIME_BLOCKER_EVENTS = {
    "LATENCY_GUARD_PREBUILD_SKIP",
    "LATENCY_GUARD_BACKGROUND_MAINTENANCE_SKIP",
    "DECISION_FEED_EVIDENCE",
    "SLO_GUARD_LIVE_CYCLE_BLOCKED",
    "SLO_FAILOVER",
    "RISK_HALT",
    "LATENCY_BREACH",
    "WS_DISCONNECTED",
    "GLOBAL_FEED_UNHEALTHY",
    "FEED_LTP_STALE",
    "FEED_DEPTH_STALE",
}
_QUOTE_SPLIT_BRAIN_EVENTS = {"QUOTE_TRUTH_SPLIT_BRAIN_REJECT"}
_OK_MARKERS = {"", "OK", "LIVE", "FRESH", "HEALTHY", "NONE"}


@dataclass(frozen=True)
class CandidateExecutabilityEvidenceReport:
    schema_version: int
    generated_by: str
    source_name: str
    session_id: str | None
    total_events_seen: int
    total_symbols_seen: int
    symbols: tuple[str, ...]
    raw_candidate_count_by_symbol: dict[str, int]
    post_scan_survivor_count_by_symbol: dict[str, int]
    real_candidate_count_by_symbol: dict[str, int]
    executable_candidate_count_by_symbol: dict[str, int]
    advisory_candidate_count_by_symbol: dict[str, int]
    blocked_candidate_count_by_symbol: dict[str, int]
    top_candidates: tuple[dict[str, object], ...]
    final_emit_block_reasons: tuple[str, ...]
    phase2_drop_counts: dict[str, int]
    trade_builder_reject_counts: dict[str, int]
    feed_runtime_blockers: dict[str, int]
    quote_truth_split_brain_count: int
    quote_truth_split_brain_examples: tuple[dict[str, object], ...]
    top_blockers_ranked: tuple[dict[str, object], ...]
    dominant_blocker: dict[str, object] | None
    recommended_next_pr_type: str
    read_only: bool = True
    append: bool = False
    is_order_action: bool = False
    broker_api_called: bool = False
    live_order_allowed: bool = False
    live_order_action: bool = False
    broker_order_action: bool = False
    runtime_wired: bool = False
    external_services_used: bool = False
    proves_trading_edge: bool = False

    @property
    def safety(self) -> dict[str, object]:
        return {
            "read_only": self.read_only,
            "append": self.append,
            "is_order_action": self.is_order_action,
            "broker_api_called": self.broker_api_called,
            "live_order_allowed": self.live_order_allowed,
            "live_order_action": self.live_order_action,
            "broker_order_action": self.broker_order_action,
            "runtime_wired": self.runtime_wired,
            "external_services_used": self.external_services_used,
            "proves_trading_edge": self.proves_trading_edge,
        }


def _normalize_reason(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_ok_marker(value: Any) -> bool:
    text = _normalize_reason(value)
    return not text or text in _OK_MARKERS or text.endswith("_OK")


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = _normalize_reason(value)
        if not text or _is_ok_marker(text):
            continue
        if text not in out:
            out.append(text)
    return out


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _extract_payload(line: str) -> dict[str, Any] | None:
    if "{" not in line or "}" not in line:
        return None
    raw = line[line.find("{") : line.rfind("}") + 1]
    try:
        parsed = ast.literal_eval(raw)
    except Exception:
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
    return parsed if isinstance(parsed, dict) else None


def _line_event_name(line: str, payload: dict[str, Any] | None) -> str:
    if isinstance(payload, dict):
        event = str(payload.get("event") or payload.get("event_type") or payload.get("type") or "").strip()
        if event:
            return event.upper()
    upper_line = line.upper()
    for marker in sorted(
        _CANDIDATE_EVENTS
        | _SUPPLY_EVENTS
        | _FINAL_EMIT_EVENTS
        | _PHASE2_EVENTS
        | _TRADE_BUILDER_REJECT_EVENTS
        | _FEED_RUNTIME_BLOCKER_EVENTS
        | _QUOTE_SPLIT_BRAIN_EVENTS,
        key=len,
        reverse=True,
    ):
        if marker in upper_line:
            return marker
    match = re.match(r".*?([A-Z][A-Z0-9_]+)", upper_line.strip())
    return match.group(1) if match else ""


def _iter_records(*, log_file: Path | None = None, events: Iterable[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if events is not None:
        for index, event in enumerate(events, start=1):
            if isinstance(event, dict):
                records.append(
                    {
                        "line_number": index,
                        "event": _line_event_name("", event),
                        "payload": dict(event),
                        "line": json.dumps(event, sort_keys=True),
                    }
                )
        return records
    if log_file is None:
        return records
    path = Path(log_file)
    if not path.exists() or not path.is_file():
        return records
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.rstrip("\n")
            if not raw.strip():
                continue
            payload = _extract_payload(raw)
            event = _line_event_name(raw, payload)
            records.append({"line_number": line_number, "event": event, "payload": payload or {}, "line": raw})
    return records


def _increment_symbol_count(counter: dict[str, int], symbol: str | None, value: Any) -> None:
    symbol_text = str(symbol or "").strip().upper()
    if not symbol_text:
        return
    counter[symbol_text] = counter.get(symbol_text, 0) + max(0, _coerce_int(value, 1))


def _append_reason(counter: Counter[str], reason: Any, *, count: int = 1) -> None:
    text = _normalize_reason(reason)
    if not text or _is_ok_marker(text):
        return
    counter[text] += max(1, int(count))


def _record_reasons_from_payload(counter: Counter[str], payload: dict[str, Any], *, keys: Iterable[str]) -> None:
    scalar_reasons: list[str] = []
    scalar_count = max(1, _coerce_int(payload.get("count") or payload.get("value"), 1))
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                _append_reason(counter, nested_key, count=_coerce_int(nested_value, 1))
        elif isinstance(value, list):
            for item in value:
                _append_reason(counter, item)
        else:
            text = _normalize_reason(value)
            if text and not _is_ok_marker(text):
                scalar_reasons.append(text)
    for reason in _dedupe_preserve_order(scalar_reasons):
        counter[reason] += scalar_count


def _candidate_row(event: str, payload: dict[str, Any]) -> dict[str, object]:
    blockers = _dedupe_preserve_order(payload.get("execution_truth_blockers") or payload.get("blockers") or [])
    candidate_status = str(
        payload.get("candidate_status")
        or payload.get("execution_status")
        or payload.get("readiness")
        or payload.get("permission")
        or payload.get("visibility_bucket")
        or event.replace("TB_TOP_", "").replace("_CANDIDATE", "")
    ).strip().lower() or "unknown"
    row = {
        "event": event,
        "symbol": str(payload.get("symbol") or payload.get("trade_symbol") or "").strip().upper() or None,
        "trade_id": str(payload.get("trade_id") or payload.get("candidate_id") or "").strip() or None,
        "strategy_family": payload.get("strategy_family"),
        "candidate_status": candidate_status,
        "execution_status": str(payload.get("execution_status") or "").strip().lower() or None,
        "execution_entry_status": str(payload.get("execution_entry_status") or "").strip().lower() or None,
        "permission": str(payload.get("permission") or "").strip().upper() or None,
        "final_action": str(payload.get("final_action") or "").strip().upper() or None,
        "readiness": str(payload.get("readiness") or "").strip().upper() or None,
        "execution_allowed": bool(payload.get("execution_allowed")),
        "eligible_for_execution": bool(
            payload.get("eligible_for_execution") if payload.get("eligible_for_execution") is not None else payload.get("execution_allowed")
        ),
        "reportable_executable": bool(payload.get("reportable_executable")),
        "reason": payload.get("reason") or payload.get("message") or payload.get("candidate_reason"),
        "final_emit_block_reason": payload.get("final_emit_block_reason") or payload.get("final_emit_abort_reason"),
        "execution_truth_blockers": blockers,
    }
    if row["execution_status"] is None:
        row["execution_status"] = candidate_status
    if row["execution_entry_status"] is None:
        row["execution_entry_status"] = candidate_status
    if row["permission"] is None:
        row["permission"] = "EXECUTE" if candidate_status == "executable" else "BLOCK"
    if row["final_action"] is None:
        row["final_action"] = "EXECUTE" if candidate_status == "executable" else "BLOCK"
    if row["readiness"] is None:
        row["readiness"] = "READY" if candidate_status == "executable" else "BLOCKED"
    return row


def _candidate_status_bucket(status: str) -> str:
    status_text = str(status or "").strip().lower()
    if status_text in {"executable", "ready"}:
        return "executable"
    if status_text in {"advisory", "advisory_only"}:
        return "advisory"
    if status_text in {"blocked", "block", "queue_only"}:
        return "blocked"
    if status_text in {"real"}:
        return "real"
    return "unknown"


def _dominant_recommendation(reason: str | None) -> str:
    reason_text = _normalize_reason(reason)
    if not reason_text:
        return "CANDIDATE_EXECUTABILITY_EVIDENCE"
    if "STALE_OPTION_LTP" in reason_text or "LTP_STALE" in reason_text:
        return "STALE_OPTION_LTP_PROVENANCE"
    if "LATENCY_GUARD" in reason_text:
        return "LATENCY_GUARD_PROVENANCE"
    if "HARD_EXECUTION" in reason_text:
        return "HARD_EXECUTION_DROP_EXPLAINER"
    if "CONFIDENCE_RAW_GATE" in reason_text or "NO_VIABLE_CANDIDATES" in reason_text or "NO_CANDIDATE_PATH" in reason_text:
        return "CONFIDENCE_GATE_CALIBRATION_EVIDENCE"
    if "REGIME_UNSTABLE" in reason_text:
        return "REGIME_UNSTABLE_EVIDENCE"
    if "QUOTE_TRUTH_SPLIT_BRAIN_REJECT" in reason_text:
        return "QUOTE_TRUTH_SPLIT_BRAIN_EVIDENCE"
    if any(marker in reason_text for marker in ("WS_DISCONNECTED", "GLOBAL_FEED_UNHEALTHY", "FEED_LTP_STALE", "FEED_DEPTH_STALE")):
        return "STALE_OPTION_LTP_PROVENANCE"
    return "CANDIDATE_EXECUTABILITY_EVIDENCE"


def build_candidate_executability_evidence(
    *,
    log_file: str | Path | None = None,
    events: Iterable[dict[str, Any]] | None = None,
    source_name: str | None = None,
    session_id: str | None = None,
) -> CandidateExecutabilityEvidenceReport:
    records = _iter_records(log_file=Path(log_file) if log_file is not None else None, events=events)
    raw_counts: dict[str, int] = {}
    post_scan_counts: dict[str, int] = {}
    real_counts: dict[str, int] = {}
    executable_counts: dict[str, int] = {}
    advisory_counts: dict[str, int] = {}
    blocked_counts: dict[str, int] = {}
    top_candidates: list[dict[str, object]] = []
    final_emit_reasons: Counter[str] = Counter()
    phase2_drop_counts: Counter[str] = Counter()
    trade_builder_reject_counts: Counter[str] = Counter()
    feed_runtime_blockers: Counter[str] = Counter()
    top_blockers: Counter[str] = Counter()
    quote_truth_split_brain_count = 0
    quote_truth_split_brain_examples: list[dict[str, object]] = []
    symbols: set[str] = set()

    for record in records:
        event = str(record.get("event") or "").strip().upper()
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        if not isinstance(payload, dict):
            payload = {}
        symbol = str(payload.get("symbol") or payload.get("trade_symbol") or "").strip().upper() or None
        if symbol:
            symbols.add(symbol)
        if event in _SUPPLY_EVENTS:
            if event == "RAW_CANDIDATE_COUNT":
                _increment_symbol_count(raw_counts, symbol, payload.get("count") or payload.get("raw_count") or payload.get("value"))
            elif event == "POST_SCAN_SURVIVOR_COUNT":
                _increment_symbol_count(post_scan_counts, symbol, payload.get("count") or payload.get("value"))
            elif event == "POST_REAL_FILTER_COUNT" or event == "TB_RANKED_COUNT_REAL":
                _increment_symbol_count(real_counts, symbol, payload.get("count") or payload.get("value"))
            elif event == "POST_EXECUTABLE_FILTER_COUNT" or event == "TB_RANKED_COUNT_EXECUTABLE":
                _increment_symbol_count(executable_counts, symbol, payload.get("count") or payload.get("value"))
            elif event == "TB_RANKED_COUNT_ADVISORY":
                _increment_symbol_count(advisory_counts, symbol, payload.get("count") or payload.get("value"))
            elif event == "TB_RANKED_COUNT_BLOCKED":
                _increment_symbol_count(blocked_counts, symbol, payload.get("count") or payload.get("value"))
        if event in _CANDIDATE_EVENTS:
            row = _candidate_row(event, payload)
            top_candidates.append(row)
            if row.get("symbol"):
                symbols.add(str(row["symbol"]))
            _append_reason(top_blockers, row.get("final_emit_block_reason"))
            for blocker in row.get("execution_truth_blockers") or []:
                _append_reason(top_blockers, blocker)
        if event in _FINAL_EMIT_EVENTS:
            _record_reasons_from_payload(final_emit_reasons, payload, keys=("reason", "final_emit_block_reason", "final_emit_abort_reason", "block_reason"))
        if event in _PHASE2_EVENTS:
            _record_reasons_from_payload(phase2_drop_counts, payload, keys=("drop_counts", "reason", "block_reason", "drop_reason"))
        if event in _TRADE_BUILDER_REJECT_EVENTS:
            _record_reasons_from_payload(trade_builder_reject_counts, payload, keys=("reject_counts", "reason", "reason_code", "block_reason", "drop_reason", "counts"))
        if event in _FEED_RUNTIME_BLOCKER_EVENTS:
            _record_reasons_from_payload(
                feed_runtime_blockers,
                payload,
                keys=(
                    "reason",
                    "reasons",
                    "blockers",
                    "feed_truth_reasons",
                    "feed_runtime_blockers",
                    "option_feed_block_reason",
                    "option_feed_block_reason_by_symbol",
                    "feed_block_reason_by_symbol",
                ),
            )
        if event in _QUOTE_SPLIT_BRAIN_EVENTS:
            quote_truth_split_brain_count += 1
            _append_reason(top_blockers, event)
            if symbol:
                symbols.add(symbol)
            quote_truth_split_brain_examples.append(
                {
                    "event": event,
                    "symbol": symbol,
                    "trade_id": str(payload.get("trade_id") or "").strip() or None,
                    "current_ltp": payload.get("current_ltp"),
                    "best_bid": payload.get("best_bid"),
                    "best_ask": payload.get("best_ask"),
                    "reason": payload.get("reason") or payload.get("block_reason"),
                }
            )
            _record_reasons_from_payload(top_blockers, payload, keys=("reason", "reasons", "block_reason"))
        if event == "DECISION_FEED_EVIDENCE":
            _record_reasons_from_payload(feed_runtime_blockers, payload, keys=("blockers", "reason", "reasons", "latency_guard_reason"))
        if event in _FINAL_EMIT_EVENTS:
            _record_reasons_from_payload(top_blockers, payload, keys=("reason", "final_emit_block_reason", "final_emit_abort_reason", "block_reason"))
    combined_counter: Counter[str] = Counter()
    for source in (final_emit_reasons, phase2_drop_counts, trade_builder_reject_counts, feed_runtime_blockers, top_blockers):
        for reason, count in source.items():
            combined_counter[_normalize_reason(reason)] += int(count)
    for row in top_candidates:
        for blocker in row.get("execution_truth_blockers") or []:
            combined_counter[_normalize_reason(blocker)] += 1
        if row.get("final_emit_block_reason"):
            combined_counter[_normalize_reason(row.get("final_emit_block_reason"))] += 1
    if quote_truth_split_brain_count:
        combined_counter["QUOTE_TRUTH_SPLIT_BRAIN_REJECT"] += int(quote_truth_split_brain_count)

    top_blockers_ranked = tuple(
        {"reason": reason, "count": count, "recommended_next_pr_type": _dominant_recommendation(reason)}
        for reason, count in sorted(combined_counter.items(), key=lambda item: (-item[1], item[0]))
    )
    dominant_blocker = top_blockers_ranked[0] if top_blockers_ranked else None
    recommended_next_pr_type = dominant_blocker["recommended_next_pr_type"] if dominant_blocker else "CANDIDATE_EXECUTABILITY_EVIDENCE"

    source_text = str(source_name or "").strip() or (Path(log_file).stem if log_file is not None else "candidate_executability_evidence")
    session_text = str(session_id or "").strip() or (Path(log_file).parent.name if log_file is not None else None)
    if session_text == "":
        session_text = None
    symbols_list = tuple(sorted(symbols | set(raw_counts) | set(post_scan_counts) | set(real_counts) | set(executable_counts) | set(advisory_counts) | set(blocked_counts)))
    return CandidateExecutabilityEvidenceReport(
        schema_version=CANDIDATE_EXECUTABILITY_EVIDENCE_SCHEMA_VERSION,
        generated_by="candidate_executability_evidence",
        source_name=source_text,
        session_id=session_text,
        total_events_seen=len(records),
        total_symbols_seen=len(symbols_list),
        symbols=symbols_list,
        raw_candidate_count_by_symbol=dict(sorted(raw_counts.items())),
        post_scan_survivor_count_by_symbol=dict(sorted(post_scan_counts.items())),
        real_candidate_count_by_symbol=dict(sorted(real_counts.items())),
        executable_candidate_count_by_symbol=dict(sorted(executable_counts.items())),
        advisory_candidate_count_by_symbol=dict(sorted(advisory_counts.items())),
        blocked_candidate_count_by_symbol=dict(sorted(blocked_counts.items())),
        top_candidates=tuple(top_candidates),
        final_emit_block_reasons=tuple(reason for reason, _ in sorted(final_emit_reasons.items(), key=lambda item: (-item[1], item[0]))),
        phase2_drop_counts=dict(sorted(phase2_drop_counts.items())),
        trade_builder_reject_counts=dict(sorted(trade_builder_reject_counts.items())),
        feed_runtime_blockers=dict(sorted(feed_runtime_blockers.items())),
        quote_truth_split_brain_count=int(quote_truth_split_brain_count),
        quote_truth_split_brain_examples=tuple(quote_truth_split_brain_examples),
        top_blockers_ranked=top_blockers_ranked,
        dominant_blocker=dominant_blocker,
        recommended_next_pr_type=recommended_next_pr_type,
    )


def report_to_payload(report: CandidateExecutabilityEvidenceReport) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "generated_by": report.generated_by,
        "source_name": report.source_name,
        "session_id": report.session_id,
        "total_events_seen": report.total_events_seen,
        "total_symbols_seen": report.total_symbols_seen,
        "symbols": list(report.symbols),
        "raw_candidate_count_by_symbol": dict(report.raw_candidate_count_by_symbol),
        "post_scan_survivor_count_by_symbol": dict(report.post_scan_survivor_count_by_symbol),
        "real_candidate_count_by_symbol": dict(report.real_candidate_count_by_symbol),
        "executable_candidate_count_by_symbol": dict(report.executable_candidate_count_by_symbol),
        "advisory_candidate_count_by_symbol": dict(report.advisory_candidate_count_by_symbol),
        "blocked_candidate_count_by_symbol": dict(report.blocked_candidate_count_by_symbol),
        "top_candidates": [dict(row) for row in report.top_candidates],
        "final_emit_block_reasons": list(report.final_emit_block_reasons),
        "phase2_drop_counts": dict(report.phase2_drop_counts),
        "trade_builder_reject_counts": dict(report.trade_builder_reject_counts),
        "feed_runtime_blockers": dict(report.feed_runtime_blockers),
        "quote_truth_split_brain_count": report.quote_truth_split_brain_count,
        "quote_truth_split_brain_examples": [dict(row) for row in report.quote_truth_split_brain_examples],
        "top_blockers_ranked": [dict(item) for item in report.top_blockers_ranked],
        "dominant_blocker": dict(report.dominant_blocker) if report.dominant_blocker else None,
        "recommended_next_pr_type": report.recommended_next_pr_type,
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_allowed": False,
        "live_order_action": False,
        "broker_order_action": False,
        "runtime_wired": False,
        "external_services_used": False,
        "proves_trading_edge": False,
        "safety": {
            "read_only": True,
            "append": False,
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_allowed": False,
            "live_order_action": False,
            "broker_order_action": False,
            "runtime_wired": False,
            "external_services_used": False,
            "proves_trading_edge": False,
        },
    }


def write_candidate_executability_json_report(report: CandidateExecutabilityEvidenceReport, output_path: str | Path) -> Path:
    path = Path(output_path)
    write_json_atomic(path, report_to_payload(report))
    return path


def _markdown_table(rows: list[dict[str, object]], columns: list[str]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def write_candidate_executability_markdown_report(report: CandidateExecutabilityEvidenceReport, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Candidate Executability Evidence Summary",
        "",
        f"- Schema version: {report.schema_version}",
        f"- Generated by: {report.generated_by}",
        f"- Source name: {report.source_name}",
        f"- Session id: {report.session_id or 'n/a'}",
        f"- Total events seen: {report.total_events_seen}",
        f"- Total symbols seen: {report.total_symbols_seen}",
        "",
        "## Safety",
    ]
    for key, value in report.safety.items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Symbols",
            f"- {', '.join(report.symbols) if report.symbols else 'none'}",
            "",
            "## Candidate Supply",
        ]
    )
    for symbol in report.symbols:
        lines.append(
            f"- {symbol}: raw={report.raw_candidate_count_by_symbol.get(symbol, 0)} post_scan={report.post_scan_survivor_count_by_symbol.get(symbol, 0)} "
            f"real={report.real_candidate_count_by_symbol.get(symbol, 0)} executable={report.executable_candidate_count_by_symbol.get(symbol, 0)} "
            f"advisory={report.advisory_candidate_count_by_symbol.get(symbol, 0)} blocked={report.blocked_candidate_count_by_symbol.get(symbol, 0)}"
        )
    lines.extend(
        [
            "",
            "## Top Candidates",
        ]
    )
    if report.top_candidates:
        lines.append(
            _markdown_table(
                list(report.top_candidates),
                [
                    "symbol",
                    "trade_id",
                    "strategy_family",
                    "candidate_status",
                    "execution_status",
                    "execution_entry_status",
                    "permission",
                    "final_action",
                    "readiness",
                    "execution_allowed",
                    "eligible_for_execution",
                    "reportable_executable",
                    "reason",
                    "final_emit_block_reason",
                ],
            )
        )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Final Emit Block Reasons",
            f"- {', '.join(report.final_emit_block_reasons) if report.final_emit_block_reasons else 'none'}",
            "",
            "## Phase2 Drop Counts",
        ]
    )
    for key, value in sorted(report.phase2_drop_counts.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## TradeBuilder Reject Counts",
        ]
    )
    for key, value in sorted(report.trade_builder_reject_counts.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Feed Runtime Blockers",
        ]
    )
    for key, value in sorted(report.feed_runtime_blockers.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Quote Truth",
            f"- quote_truth_split_brain_count: {report.quote_truth_split_brain_count}",
            f"- quote_truth_split_brain_examples: {json.dumps(list(report.quote_truth_split_brain_examples), sort_keys=True)}",
            "",
            "## Top Blockers",
        ]
    )
    for item in report.top_blockers_ranked:
        lines.append(f"- {item['reason']}: {item['count']} ({item['recommended_next_pr_type']})")
    lines.extend(
        [
            "",
            f"- Dominant blocker: {report.dominant_blocker['reason'] if report.dominant_blocker else 'none'}",
            f"- Recommended next PR type: {report.recommended_next_pr_type}",
            "",
            "This report is read-only and does not authorize any order action.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_candidate_executability_evidence(
    *,
    log_file: str | Path,
    output_dir: str | Path,
    source_name: str | None = None,
    session_id: str | None = None,
) -> tuple[Path, Path, CandidateExecutabilityEvidenceReport]:
    report = build_candidate_executability_evidence(log_file=log_file, source_name=source_name, session_id=session_id)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = write_candidate_executability_json_report(report, output_root / "candidate_executability_summary.json")
    markdown_path = write_candidate_executability_markdown_report(report, output_root / "candidate_executability_summary.md")
    return json_path, markdown_path, report


__all__ = [
    "CANDIDATE_EXECUTABILITY_EVIDENCE_SCHEMA_VERSION",
    "CandidateExecutabilityEvidenceReport",
    "build_candidate_executability_evidence",
    "report_to_payload",
    "write_candidate_executability_evidence",
    "write_candidate_executability_json_report",
    "write_candidate_executability_markdown_report",
]

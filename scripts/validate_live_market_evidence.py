#!/usr/bin/env python3
"""Validate live-market feed/staleness evidence.

This script is read-only. It does not call broker APIs, submit orders, change
execution gates, mutate ranking, or touch depth subscriptions.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from core.feed_staleness_observability import build_feed_staleness_report, write_feed_staleness_report

REQUIRED_SUMMARY_FIELDS = (
    "feed_ok",
    "ws_connected",
    "subscribed_option_tokens_count",
    "visible_executable_count",
)

EXECUTABLE_TRACE_MARKERS = (
    "permission': 'EXECUTE'",
    'permission": "EXECUTE"',
    "final_action': 'EXECUTE'",
    'final_action": "EXECUTE"',
    "execution_allowed': True",
    'execution_allowed": true',
)


def _boolish(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "ok"}:
        return True
    if text in {"false", "0", "no", "n", "bad"}:
        return False
    return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _truthy_env(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_lines(path: Path) -> list[str]:
    try:
        if not path.exists() or not path.is_file():
            return []
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []


def _parse_log_dict(line: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", line)
    if not match:
        return None
    raw = match.group(0)
    try:
        parsed = ast.literal_eval(raw)
    except Exception:
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
    return parsed if isinstance(parsed, dict) else None


def scan_run_log_for_fallback_executable_traces(logs_dir: str | Path | None) -> list[dict[str, Any]]:
    """Return fallback-contract traces that later appear executable in run_live.log.

    This is conservative and read-only. It groups fallback events by symbol and
    flags later candidate/top-candidate lines for the same symbol that contain
    executable-looking markers.
    """

    if logs_dir is None:
        return []
    root = Path(logs_dir).expanduser()
    candidates = [root / "run_live.log", root.parent / "run_live.log"]
    lines: list[str] = []
    for path in candidates:
        lines = _load_lines(path)
        if lines:
            break
    if not lines:
        return []

    fallback_symbols: dict[str, dict[str, Any]] = {}
    traces: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if "CONTRACT_RESOLUTION_FALLBACK" in line:
            payload = _parse_log_dict(line) or {}
            symbol = str(payload.get("symbol") or "").strip()
            if symbol:
                fallback_symbols[symbol] = {
                    "line_number": index + 1,
                    "symbol": symbol,
                    "payload": payload,
                }
            continue

        if not fallback_symbols:
            continue
        if not any(marker in line for marker in EXECUTABLE_TRACE_MARKERS):
            continue
        if "TB_TOP" not in line and "CANDIDATE" not in line and "FINAL" not in line:
            continue

        payload = _parse_log_dict(line) or {}
        symbol = str(payload.get("symbol") or "").strip()
        if not symbol:
            for known_symbol in fallback_symbols:
                if known_symbol and known_symbol in line:
                    symbol = known_symbol
                    break
        if symbol not in fallback_symbols:
            continue
        traces.append(
            {
                "line_number": index + 1,
                "symbol": symbol,
                "fallback_line_number": fallback_symbols[symbol]["line_number"],
                "event": "fallback_contract_executable_trace",
                "payload": payload,
                "line": line[-500:],
            }
        )
    return traces


def validate_live_evidence(report: dict[str, Any], *, logs_dir: str | Path | None = None) -> dict[str, Any]:
    """Return a read-only live validation summary for an observability report."""

    summary = dict(report.get("summary") or {})
    violations: list[str] = []
    warnings: list[str] = []

    if report.get("read_only") is not True:
        violations.append("report_not_marked_read_only")
    if report.get("is_order_action") is not False:
        violations.append("report_not_marked_non_order_action")

    for field in REQUIRED_SUMMARY_FIELDS:
        if field not in summary or summary.get(field) is None:
            if field == "visible_executable_count":
                violations.append(f"missing_summary_field:{field}")
            else:
                warnings.append(f"missing_summary_field:{field}")

    feed_ok = _boolish(summary.get("feed_ok"))
    ws_connected = _boolish(summary.get("ws_connected"))
    option_count = _as_int(summary.get("subscribed_option_tokens_count"))
    visible_executable_count = _as_int(summary.get("visible_executable_count"))
    recon_daemon_running = _boolish(summary.get("recon_daemon_running"))

    if feed_ok is False:
        warnings.append("feed_not_ok")
    if ws_connected is False:
        violations.append("websocket_not_connected")
    if option_count is not None and option_count <= 0:
        violations.append("option_subscription_count_zero_or_negative")
    if visible_executable_count is not None and visible_executable_count < 0:
        violations.append("visible_executable_count_negative")

    if _truthy_env("ORDER_RECON_ENABLED", default=False) is False and recon_daemon_running is True:
        violations.append("order_recon_daemon_running_while_disabled")

    fallback_executable_traces = scan_run_log_for_fallback_executable_traces(
        logs_dir if logs_dir is not None else report.get("logs_dir")
    )
    if fallback_executable_traces:
        violations.append("fallback_contract_reached_executable_trace")

    missing_files = list(summary.get("missing_runtime_files") or [])
    errored_files = dict(summary.get("errored_runtime_files") or {})
    if missing_files:
        warnings.append("missing_runtime_files:" + ",".join(sorted(str(x) for x in missing_files)))
    if errored_files:
        violations.append("errored_runtime_files:" + ",".join(sorted(str(k) for k in errored_files)))

    blocker_counts = dict(
        ((report.get("blocker_evidence") or {}).get("suggestions_tail_blocker_counts") or {})
    )
    status_counts = dict(((report.get("status_counts") or {}).get("suggestions_tail_status_counts") or {}))

    if not blocker_counts:
        warnings.append("no_suggestion_blocker_counts_visible")
    if not status_counts:
        warnings.append("no_suggestion_status_counts_visible")

    # This script cannot prove live market was actually open. It only validates
    # that required evidence exists and is sane. Human/live-session context is
    # still required for a final PASS.
    if violations:
        verdict = "FAIL"
    elif warnings:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "PASS_CANDIDATE"

    return {
        "schema_version": 1,
        "generated_epoch": time.time(),
        "read_only": True,
        "is_order_action": False,
        "verdict": verdict,
        "violations": violations,
        "warnings": warnings,
        "summary": {
            "feed_ok": summary.get("feed_ok"),
            "ws_connected": summary.get("ws_connected"),
            "subscribed_option_tokens_count": summary.get("subscribed_option_tokens_count"),
            "visible_executable_count": summary.get("visible_executable_count"),
            "recon_daemon_running": summary.get("recon_daemon_running"),
            "suggestions_tail_rows": summary.get("suggestions_tail_rows"),
            "events_tail_rows": summary.get("events_tail_rows"),
        },
        "fallback_executable_trace_count": len(fallback_executable_traces),
        "fallback_executable_traces": fallback_executable_traces[:20],
        "top_suggestion_blockers": blocker_counts,
        "suggestion_status_counts": status_counts,
        "source_observability_report": report.get("logs_dir"),
    }


def write_live_validation_report(
    logs_dir: str | Path | None = None,
    output_path: str | Path | None = None,
) -> Path:
    observability_path = write_feed_staleness_report(logs_dir)
    report = build_feed_staleness_report(logs_dir)
    validation = validate_live_evidence(report, logs_dir=logs_dir)
    validation["observability_report_path"] = str(observability_path)

    if output_path is None:
        out = observability_path.parent / "live_market_validation_evidence_latest.json"
    else:
        out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate live-market feed/staleness evidence")
    parser.add_argument("--logs-dir", default=None, help="Runtime logs directory; defaults to core.paths.logs_dir()")
    parser.add_argument("--output", default=None, help="Output JSON path")
    parser.add_argument("--print", action="store_true", help="Print validation JSON to stdout")
    args = parser.parse_args()

    if args.print:
        report = build_feed_staleness_report(args.logs_dir)
        validation = validate_live_evidence(report, logs_dir=args.logs_dir)
        print(json.dumps(validation, indent=2, sort_keys=True))
        return 0

    out = write_live_validation_report(args.logs_dir, args.output)
    print(f"Wrote live market validation evidence: {Path(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

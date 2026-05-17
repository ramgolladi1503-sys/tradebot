#!/usr/bin/env python3
"""Validate live-market feed/staleness evidence.

This script is read-only. It does not call broker APIs, submit orders, change
execution gates, mutate ranking, or touch depth subscriptions.
"""

from __future__ import annotations

import argparse
import json
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


def validate_live_evidence(report: dict[str, Any]) -> dict[str, Any]:
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
            warnings.append(f"missing_summary_field:{field}")

    feed_ok = _boolish(summary.get("feed_ok"))
    ws_connected = _boolish(summary.get("ws_connected"))
    option_count = _as_int(summary.get("subscribed_option_tokens_count"))

    if feed_ok is False:
        warnings.append("feed_not_ok")
    if ws_connected is False:
        violations.append("websocket_not_connected")
    if option_count is not None and option_count <= 0:
        violations.append("option_subscription_count_zero_or_negative")

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
            "suggestions_tail_rows": summary.get("suggestions_tail_rows"),
            "events_tail_rows": summary.get("events_tail_rows"),
        },
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
    validation = validate_live_evidence(report)
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
        validation = validate_live_evidence(report)
        print(json.dumps(validation, indent=2, sort_keys=True))
        return 0

    out = write_live_validation_report(args.logs_dir, args.output)
    print(f"Wrote live market validation evidence: {Path(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

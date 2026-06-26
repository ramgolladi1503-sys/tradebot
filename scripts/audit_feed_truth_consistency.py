#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.feed_truth_audit import (
    render_feed_truth_audit_markdown,
    write_feed_truth_audit_report,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit feed truth consistency from live evidence files."
    )
    parser.add_argument(
        "--log-file",
        required=True,
        help="Path to live_console.log or equivalent event log.",
    )
    parser.add_argument(
        "--runtime-file",
        required=True,
        help="Path to runtime/feed_runtime_latest.json or equivalent runtime truth snapshot.",
    )
    parser.add_argument("--out", required=True, help="Report output path.")
    parser.add_argument(
        "--format",
        default="json",
        choices=("json", "markdown"),
        help="Output format for the audit report.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail closed when any required input source is missing or unreadable.",
    )
    return parser.parse_args()


def _missing_required_source_codes(report: dict[str, object]) -> list[str]:
    codes: list[str] = []
    for warning in report.get("warnings") or []:
        if not isinstance(warning, dict):
            continue
        code = str(warning.get("code") or "").strip()
        if code in {"missing_log_file", "missing_runtime_file"}:
            codes.append(code)
    return codes


def main() -> int:
    args = _parse_args()
    out_path, report = write_feed_truth_audit_report(
        log_file=args.log_file,
        runtime_file=args.runtime_file,
        out=args.out,
        fmt=args.format,
        strict=args.strict,
    )
    report["strict"] = bool(args.strict)
    if args.format == "markdown":
        Path(out_path).write_text(
            render_feed_truth_audit_markdown(report), encoding="utf-8"
        )
    else:
        Path(out_path).write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )

    missing_required_sources = _missing_required_source_codes(report)
    if args.strict and missing_required_sources:
        print(
            "feed truth audit: strict mode failed closed due to missing required source(s): "
            + ", ".join(sorted(set(missing_required_sources))),
            file=sys.stderr,
        )
        return 2

    contradiction_count = len(report.get("contradictions") or [])
    if contradiction_count:
        print(
            f"feed truth audit: {contradiction_count} contradiction(s) detected",
            file=sys.stderr,
        )
        return 1

    print(f"feed truth audit report written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

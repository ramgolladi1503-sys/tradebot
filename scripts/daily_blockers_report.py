from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from core.learning_paths import suggestion_log_paths


IST = ZoneInfo("Asia/Kolkata")


def _coerce_day(value: Any | None) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return datetime.now(tz=IST).date() - timedelta(days=1)
    return date.fromisoformat(text)


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _parse_ts_utc(row: Mapping[str, Any]) -> datetime | None:
    for key in ("timestamp_epoch_ms", "ts_epoch_ms"):
        value = row.get(key)
        if value is None:
            continue
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=ZoneInfo("UTC"))
        except Exception:
            continue
    for key in ("timestamp_epoch", "ts_epoch"):
        value = row.get(key)
        if value is None:
            continue
        try:
            return datetime.fromtimestamp(float(value), tz=ZoneInfo("UTC"))
        except Exception:
            continue
    for key in ("timestamp_utc_iso", "timestamp", "ts_utc", "ts_ist"):
        raw = row.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except Exception:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(ZoneInfo("UTC"))
    return None


def _iter_jsonl(paths: Sequence[Path], target_day: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    ts_utc = _parse_ts_utc(payload)
                    if ts_utc is None:
                        continue
                    if ts_utc.astimezone(IST).date() != target_day:
                        continue
                    rows.append(payload)
        except Exception:
            continue
    return rows


def _top_counts(counter: Counter[str], *, limit: int = 10) -> list[dict[str, Any]]:
    return [
        {"name": name, "count": int(count)}
        for name, count in counter.most_common(limit)
    ]


def build_blockers_report(
    rows: Sequence[Mapping[str, Any]], day: date | str
) -> dict[str, Any]:
    target_day = _coerce_day(day)
    permission_reason_counts: Counter[str] = Counter()
    entry_status_counts: Counter[str] = Counter()
    combined_counts: Counter[str] = Counter()
    orb_bias_counts: Counter[str] = Counter()
    orb_factor_counts: Counter[str] = Counter()

    below_high_due_to_orb = 0
    high_threshold = 0.65

    for row in rows:
        decision_trace = row.get("decision_trace") if isinstance(row, dict) else None
        if not isinstance(decision_trace, dict):
            decision_trace = {}

        permission_reason = str(
            row.get("permission_reason")
            or decision_trace.get("permission_reason")
            or "UNKNOWN"
        )
        entry_status = str(
            row.get("entry_status") or decision_trace.get("entry_status") or "UNKNOWN"
        )
        permission_reason_counts[permission_reason] += 1
        entry_status_counts[entry_status] += 1
        combined_counts[f"{permission_reason} + {entry_status}"] += 1

        orb_bias = str(
            decision_trace.get("orb_bias") or row.get("orb_bias") or "UNKNOWN"
        )
        orb_bias_counts[orb_bias] += 1

        orb_factor = _coerce_float(decision_trace.get("orb_factor"))
        if orb_factor is not None:
            orb_factor_counts[f"{orb_factor:.2f}"] += 1

        global_conf = _coerce_float(
            decision_trace.get("global_conf")
            if decision_trace.get("global_conf") is not None
            else row.get("global_confidence")
        )
        if global_conf is None or global_conf >= high_threshold:
            continue
        if orb_factor is None or orb_factor <= 0:
            continue
        try:
            conf_without_orb = global_conf / orb_factor
        except Exception:
            continue
        if conf_without_orb >= high_threshold:
            below_high_due_to_orb += 1

    return {
        "day": target_day.isoformat(),
        "total_rows": int(len(rows)),
        "permission_reason_top10": _top_counts(permission_reason_counts, limit=10),
        "entry_status_top10": _top_counts(entry_status_counts, limit=10),
        "combined_blockers_top10": _top_counts(combined_counts, limit=10),
        "orb_bias_distribution": _top_counts(orb_bias_counts, limit=10),
        "orb_factor_distribution": _top_counts(orb_factor_counts, limit=10),
        "below_high_execute_due_to_orb_factor": int(below_high_due_to_orb),
        "high_execute_threshold": float(high_threshold),
    }


def render_blockers_md(report: Mapping[str, Any]) -> str:
    lines = [
        f"# Blockers Report ({report.get('day')})",
        "",
        "## Summary",
        f"- Total rows: {int(report.get('total_rows') or 0)}",
        f"- High execute threshold: {float(report.get('high_execute_threshold') or 0.65):.2f}",
        (
            "- Below high execute due to orb factor: "
            f"{int(report.get('below_high_execute_due_to_orb_factor') or 0)}"
        ),
        "",
        "## Permission Reasons (Top 10)",
        "| Reason | Count |",
        "|---|---:|",
    ]
    for row in list(report.get("permission_reason_top10") or []):
        lines.append(f"| {row.get('name')} | {int(row.get('count') or 0)} |")

    lines.extend(
        [
            "",
            "## Entry Status (Top 10)",
            "| Entry Status | Count |",
            "|---|---:|",
        ]
    )
    for row in list(report.get("entry_status_top10") or []):
        lines.append(f"| {row.get('name')} | {int(row.get('count') or 0)} |")

    lines.extend(
        [
            "",
            "## Combined Blockers (Top 10)",
            "| Blocker | Count |",
            "|---|---:|",
        ]
    )
    for row in list(report.get("combined_blockers_top10") or []):
        lines.append(f"| {row.get('name')} | {int(row.get('count') or 0)} |")

    lines.extend(
        [
            "",
            "## Orb Diagnostics",
            "### Orb Bias Distribution",
            "| Orb Bias | Count |",
            "|---|---:|",
        ]
    )
    for row in list(report.get("orb_bias_distribution") or []):
        lines.append(f"| {row.get('name')} | {int(row.get('count') or 0)} |")

    lines.extend(
        [
            "",
            "### Orb Factor Distribution",
            "| Orb Factor | Count |",
            "|---|---:|",
        ]
    )
    for row in list(report.get("orb_factor_distribution") or []):
        lines.append(f"| {row.get('name')} | {int(row.get('count') or 0)} |")

    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def write_blockers_report(
    report: Mapping[str, Any], out_dir: Path
) -> tuple[Path, Path]:
    target_day = _coerce_day(report.get("day"))
    day_dir = Path(out_dir) / target_day.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    json_path = day_dir / "blockers.json"
    md_path = day_dir / "blockers.md"
    _atomic_write(
        json_path,
        json.dumps(dict(report), ensure_ascii=True, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write(md_path, render_blockers_md(report))
    return md_path, json_path


def run_blockers_report(
    day: date | str,
    *,
    source_paths: Iterable[Path] | None = None,
    out_base: Path | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    target_day = _coerce_day(day)
    paths = list(source_paths or suggestion_log_paths())
    rows = _iter_jsonl(paths, target_day)
    report = build_blockers_report(rows, target_day)
    out_root = (
        Path(out_base) if out_base is not None else Path("runtime/analytics/reports")
    )
    md_path, json_path = write_blockers_report(report, out_root)
    return report, md_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate blockers rollup from suggestion logs"
    )
    parser.add_argument(
        "--date",
        dest="day",
        default=None,
        help="Target date (YYYY-MM-DD). Defaults to yesterday (IST).",
    )
    parser.add_argument(
        "--source",
        dest="source_paths",
        action="append",
        default=[],
        help="Optional JSONL source path (can be provided multiple times).",
    )
    parser.add_argument(
        "--out-base",
        dest="out_base",
        default="runtime/analytics/reports",
        help="Report output base directory.",
    )
    args = parser.parse_args()

    paths = [Path(p) for p in args.source_paths] if args.source_paths else None
    report, md_path, json_path = run_blockers_report(
        args.day, source_paths=paths, out_base=Path(args.out_base)
    )
    print(
        json.dumps(
            {"day": report.get("day"), "md": str(md_path), "json": str(json_path)},
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

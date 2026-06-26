#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.learning_paths import (
    canonical_suggestions_log_path,
    rejected_candidates_paths,
)


_SCORE_METADATA_FIELDS = ("rank_score", "opportunity_score", "score_breakdown")


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _unique_paths(paths: list[Path] | None) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths or []:
        normalized = str(Path(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(Path(path))
    return out


def _read_tail_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for raw in lines[-int(limit) :]:
        line = str(raw or "").strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _row_epoch(row: dict[str, Any]) -> float:
    for key in ("ts_epoch", "timestamp_epoch", "timestamp_epoch_ms"):
        value = _safe_float(row.get(key))
        if value is None:
            continue
        if key.endswith("_ms"):
            return float(value) / 1000.0
        return float(value)
    return 0.0


def _strategy_family(row: dict[str, Any]) -> str:
    return str(row.get("strategy_family") or "unknown").strip() or "unknown"


def _candidate_type(row: dict[str, Any]) -> str:
    return str(row.get("candidate_type") or "unknown").strip() or "unknown"


def _final_action(row: dict[str, Any]) -> str:
    return str(row.get("final_action") or "UNKNOWN").strip().upper() or "UNKNOWN"


def _score_metadata_missing_fields(row: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if _safe_float(row.get("rank_score")) is None:
        missing.append("rank_score")
    if _safe_float(row.get("opportunity_score")) is None:
        missing.append("opportunity_score")
    breakdown = row.get("score_breakdown")
    if not isinstance(breakdown, dict) or not breakdown:
        missing.append("score_breakdown")
    return missing


def _collect_recent_rows(
    *,
    suggestions_paths: list[Path],
    rejected_paths: list[Path],
    limit: int,
) -> list[dict[str, Any]]:
    recent_rows: list[dict[str, Any]] = []
    for source, paths in (
        ("suggestions", suggestions_paths),
        ("rejected", rejected_paths),
    ):
        for path in _unique_paths(paths):
            for row in _read_tail_jsonl(path, limit):
                tagged = dict(row)
                tagged["_source"] = source
                tagged["_source_path"] = str(path)
                recent_rows.append(tagged)
    recent_rows.sort(
        key=lambda row: (
            -_row_epoch(row),
            str(row.get("trade_id") or ""),
            str(row.get("_source") or ""),
        )
    )
    return recent_rows[: max(0, int(limit))]


def build_candidate_pipeline_report(
    *,
    suggestions_paths: list[Path] | None = None,
    rejected_paths: list[Path] | None = None,
    limit: int = 200,
    top_n: int = 10,
) -> dict[str, Any]:
    suggestion_sources = _unique_paths(
        suggestions_paths or [canonical_suggestions_log_path()]
    )
    rejected_sources = _unique_paths(
        rejected_paths or list(rejected_candidates_paths())
    )
    rows = _collect_recent_rows(
        suggestions_paths=suggestion_sources,
        rejected_paths=rejected_sources,
        limit=max(1, int(limit)),
    )
    final_action_distribution = Counter()
    strategy_family_distribution = Counter()
    candidate_type_distribution = Counter()
    rank_score_present_count = 0
    missing_score_metadata_rows: list[dict[str, Any]] = []

    for row in rows:
        final_action_distribution[_final_action(row)] += 1
        strategy_family_distribution[_strategy_family(row)] += 1
        candidate_type_distribution[_candidate_type(row)] += 1
        if _safe_float(row.get("rank_score")) is not None:
            rank_score_present_count += 1
        missing_fields = _score_metadata_missing_fields(row)
        if missing_fields:
            missing_score_metadata_rows.append(
                {
                    "trade_id": row.get("trade_id"),
                    "source": row.get("_source"),
                    "source_path": row.get("_source_path"),
                    "final_action": _final_action(row),
                    "candidate_status": row.get("candidate_status"),
                    "strategy_family": _strategy_family(row),
                    "candidate_type": _candidate_type(row),
                    "missing_fields": missing_fields,
                }
            )

    ranked_rows = [
        row for row in rows if _safe_float(row.get("rank_score")) is not None
    ]
    ranked_rows.sort(
        key=lambda row: (
            -float(_safe_float(row.get("rank_score")) or 0.0),
            -float(_safe_float(row.get("opportunity_score")) or 0.0),
            str(row.get("trade_id") or ""),
        )
    )
    top_ranked = [
        {
            "trade_id": row.get("trade_id"),
            "source": row.get("_source"),
            "final_action": _final_action(row),
            "candidate_status": row.get("candidate_status"),
            "rank_score": float(_safe_float(row.get("rank_score")) or 0.0),
            "opportunity_score": _safe_float(row.get("opportunity_score")),
            "strategy_family": _strategy_family(row),
            "candidate_type": _candidate_type(row),
            "symbol": row.get("symbol"),
        }
        for row in ranked_rows[: max(1, int(top_n))]
    ]

    return {
        "total_rows": len(rows),
        "sources": {
            "suggestions": [str(path) for path in suggestion_sources],
            "rejected": [str(path) for path in rejected_sources],
        },
        "final_action_distribution": dict(sorted(final_action_distribution.items())),
        "rank_score_present_count": rank_score_present_count,
        "rank_score_missing_count": len(rows) - rank_score_present_count,
        "strategy_family_distribution": dict(
            sorted(strategy_family_distribution.items())
        ),
        "candidate_type_distribution": dict(
            sorted(candidate_type_distribution.items())
        ),
        "top_ranked": top_ranked,
        "rows_missing_score_metadata": missing_score_metadata_rows,
    }


def _render_distribution(title: str, values: dict[str, Any]) -> list[str]:
    lines = [title]
    if not values:
        lines.append("  - none")
        return lines
    for key, value in values.items():
        lines.append(f"  - {key}: {value}")
    return lines


def render_candidate_pipeline_report(report: dict[str, Any]) -> str:
    lines = [
        "Candidate Pipeline Verification",
        f"Total rows: {int(report.get('total_rows') or 0)}",
        f"Rank score present: {int(report.get('rank_score_present_count') or 0)}",
        f"Rank score missing: {int(report.get('rank_score_missing_count') or 0)}",
        "Sources:",
    ]
    sources = report.get("sources") or {}
    for label in ("suggestions", "rejected"):
        entries = list((sources.get(label) or []))
        if not entries:
            lines.append(f"  - {label}: none")
            continue
        for path in entries:
            lines.append(f"  - {label}: {path}")
    lines.extend(
        _render_distribution(
            "Final action distribution:",
            dict(report.get("final_action_distribution") or {}),
        )
    )
    lines.extend(
        _render_distribution(
            "Strategy family distribution:",
            dict(report.get("strategy_family_distribution") or {}),
        )
    )
    lines.extend(
        _render_distribution(
            "Candidate type distribution:",
            dict(report.get("candidate_type_distribution") or {}),
        )
    )
    lines.append("Top 10 by rank_score:")
    top_ranked = list(report.get("top_ranked") or [])
    if not top_ranked:
        lines.append("  - none")
    else:
        for index, row in enumerate(top_ranked, start=1):
            lines.append(
                "  "
                + f"{index}. trade_id={row.get('trade_id')} source={row.get('source')} "
                + f"rank_score={row.get('rank_score')} opportunity_score={row.get('opportunity_score')} "
                + f"final_action={row.get('final_action')} candidate_status={row.get('candidate_status')} "
                + f"strategy_family={row.get('strategy_family')} candidate_type={row.get('candidate_type')} "
                + f"symbol={row.get('symbol')}"
            )
    lines.append("Rows missing score metadata:")
    missing_rows = list(report.get("rows_missing_score_metadata") or [])
    if not missing_rows:
        lines.append("  - none")
    else:
        for row in missing_rows:
            lines.append(
                "  "
                + f"- trade_id={row.get('trade_id')} source={row.get('source')} "
                + f"final_action={row.get('final_action')} candidate_status={row.get('candidate_status')} "
                + f"strategy_family={row.get('strategy_family')} candidate_type={row.get('candidate_type')} "
                + f"missing_fields={','.join(row.get('missing_fields') or [])}"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify whether candidate generation, scoring, and ranking are alive in runtime logs."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum number of recent rows to inspect across suggestions and rejected logs.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top-ranked rows to print.",
    )
    parser.add_argument(
        "--suggestions-path",
        action="append",
        default=[],
        help="Optional suggestions JSONL path override. May be passed multiple times.",
    )
    parser.add_argument(
        "--rejected-path",
        action="append",
        default=[],
        help="Optional rejected-candidates JSONL path override. May be passed multiple times.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON instead of human-readable text.",
    )
    args = parser.parse_args()

    report = build_candidate_pipeline_report(
        suggestions_paths=[Path(path) for path in args.suggestions_path]
        if args.suggestions_path
        else None,
        rejected_paths=[Path(path) for path in args.rejected_path]
        if args.rejected_path
        else None,
        limit=max(1, int(args.limit)),
        top_n=max(1, int(args.top)),
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_candidate_pipeline_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

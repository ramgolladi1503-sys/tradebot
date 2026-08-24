#!/usr/bin/env python3
"""Run the frozen failed-discovery hypothesis on a local futures corpus.

This command is research-only. It measures the underlying phenomenon and emits
JSON evidence. It does not construct trades, consume option data, or grant any
strategy/paper/live state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from .detector import Bar, DEFAULT_CONFIG, detect_failed_discoveries
from .evaluation import HORIZONS, classify_support, match_controls, summarize_pairs

IST = ZoneInfo("Asia/Kolkata")
EXPECTED_PARTIAL_CORPUS_SHA256 = "8120d53a270ef2d5ebe1e94e800c8cd289df6e4081d7fa019e7c9ca0bd5bd92b"
EXPECTED_PARTIAL_CORPUS_SIZE = 467857
EXPECTED_PARTIAL_CORPUS_DATE_SPAN = ("2026-05-12", "2026-07-21")
EXPECTED_PARTIAL_CORPUS_SESSION_COUNT = 49


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        ts = value
    else:
        text = str(value).strip()
        if not text:
            raise ValueError("MISSING_TIMESTAMP")
        text = text.replace("Z", "+00:00")
        ts = datetime.fromisoformat(text)
    if ts.tzinfo is None:
        raise ValueError("TIMESTAMP_TIMEZONE_REQUIRED")
    return ts.astimezone(IST)


def _float(row: Mapping[str, Any], key: str) -> float:
    value = row.get(key)
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"INVALID_{key.upper()}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"NON_FINITE_{key.upper()}")
    return parsed


def _row_to_bar(row: Mapping[str, Any]) -> Bar:
    timestamp_value = None
    for key in ("timestamp", "ts", "datetime", "date"):
        if row.get(key) is not None:
            timestamp_value = row.get(key)
            break
    if timestamp_value is None:
        raise ValueError("TIMESTAMP_COLUMN_REQUIRED")
    return Bar(
        ts=_parse_ts(timestamp_value),
        open=_float(row, "open"),
        high=_float(row, "high"),
        low=_float(row, "low"),
        close=_float(row, "close"),
        volume=_float(row, "volume"),
    )


def _load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        import csv

        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix in {".json", ".jsonl"}:
        if suffix == ".jsonl":
            rows: list[dict[str, Any]] = []
            for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                text = raw.strip()
                if not text:
                    continue
                payload = json.loads(text)
                if not isinstance(payload, Mapping):
                    raise ValueError(f"JSONL_OBJECT_REQUIRED:{line_no}")
                rows.append(dict(payload))
            return rows
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, Mapping) and isinstance(payload.get("rows"), list):
            payload = payload["rows"]
        if not isinstance(payload, list) or not all(isinstance(row, Mapping) for row in payload):
            raise ValueError("JSON_OBJECT_LIST_REQUIRED")
        return [dict(row) for row in payload]
    if suffix == ".parquet":
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError(
                "PARQUET_REQUIRES_PANDAS_AND_PYARROW: install pandas pyarrow in the research environment"
            ) from exc
        frame = pd.read_parquet(path)
        return frame.to_dict(orient="records")
    raise ValueError(f"UNSUPPORTED_INPUT_FORMAT:{suffix}")


def load_sessions(path: Path) -> dict[datetime, tuple[Bar, ...]]:
    rows = _load_rows(path)
    if not rows:
        raise ValueError("EMPTY_CORPUS")
    sessions_by_date: dict[Any, list[Bar]] = {}
    for row in rows:
        bar = _row_to_bar(row)
        sessions_by_date.setdefault(bar.ts.date(), []).append(bar)

    sessions: dict[datetime, tuple[Bar, ...]] = {}
    for session_date, bars in sorted(sessions_by_date.items()):
        bars.sort(key=lambda bar: bar.ts)
        session_anchor = datetime.combine(session_date, datetime.min.time(), tzinfo=IST)
        sessions[session_anchor] = tuple(bars)
    return sessions


def _month_concentration(event_timestamps: Iterable[datetime]) -> dict[str, Any]:
    counts = Counter(ts.strftime("%Y-%m") for ts in event_timestamps)
    total = sum(counts.values())
    shares = {month: count / total for month, count in sorted(counts.items())} if total else {}
    return {
        "counts": dict(sorted(counts.items())),
        "shares": shares,
        "max_single_month_share": max(shares.values()) if shares else None,
    }


def _jsonable_summary(summary: Any) -> dict[str, Any]:
    payload = asdict(summary)
    for field in (
        "event_median_directional_bps",
        "control_median_directional_bps",
        "directional_uplift_bps",
    ):
        payload[field] = {str(k): v for k, v in payload[field].items()}
    return payload


def run(
    path: Path,
    *,
    expected_sha256: str | None,
    partition: str,
    known_partial_corpus: bool,
) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("REGULAR_INPUT_FILE_REQUIRED")
    actual_sha = sha256_file(path)
    if expected_sha256 and actual_sha.lower() != expected_sha256.lower():
        raise ValueError(
            f"INPUT_SHA256_MISMATCH:expected={expected_sha256}:actual={actual_sha}"
        )

    if known_partial_corpus:
        if actual_sha != EXPECTED_PARTIAL_CORPUS_SHA256:
            raise ValueError("KNOWN_PARTIAL_CORPUS_SHA256_MISMATCH")
        if path.stat().st_size != EXPECTED_PARTIAL_CORPUS_SIZE:
            raise ValueError("KNOWN_PARTIAL_CORPUS_SIZE_MISMATCH")
        if partition != "DEV":
            raise ValueError("KNOWN_PARTIAL_CORPUS_DEV_ONLY")

    sessions = load_sessions(path)
    all_events = []
    for bars in sessions.values():
        all_events.extend(detect_failed_discoveries(bars, DEFAULT_CONFIG))
    pairs = match_controls(sessions, sessions, DEFAULT_CONFIG)
    summary = summarize_pairs(pairs)
    preliminary_verdict = classify_support(summary)
    concentration = _month_concentration(pair.event.ts for pair in pairs)

    dates = sorted(anchor.date().isoformat() for anchor in sessions)
    known_partial_identity_ok = None
    if known_partial_corpus:
        known_partial_identity_ok = (
            len(sessions) == EXPECTED_PARTIAL_CORPUS_SESSION_COUNT
            and bool(dates)
            and (dates[0], dates[-1]) == EXPECTED_PARTIAL_CORPUS_DATE_SPAN
        )
        if not known_partial_identity_ok:
            raise ValueError("KNOWN_PARTIAL_CORPUS_SESSION_IDENTITY_MISMATCH")

    # A DEV-only run can reject or expose insufficient support, but it cannot
    # prove robustness because negative controls/OOS/oracle/holdout are absent.
    if preliminary_verdict == "ROBUSTLY_SUPPORTED":
        raise AssertionError("DEV_RUN_MUST_NOT_EMIT_ROBUSTLY_SUPPORTED")

    return {
        "schema": "vwap-failed-discovery-hypothesis-dev-report-v1",
        "hypothesis_id": "VWAP_FAILED_DISCOVERY_RETURN_TO_VALUE_H1_V1",
        "partition": partition,
        "input": {
            "path": str(path.resolve()),
            "sha256": actual_sha,
            "size_bytes": path.stat().st_size,
            "known_partial_corpus": known_partial_corpus,
            "known_partial_identity_ok": known_partial_identity_ok,
            "session_count": len(sessions),
            "date_span": [dates[0], dates[-1]] if dates else [None, None],
        },
        "frozen_formula": asdict(DEFAULT_CONFIG),
        "event_count_unmatched": len(all_events),
        "matched_pair_count": len(pairs),
        "summary": _jsonable_summary(summary),
        "month_concentration": concentration,
        "preliminary_hypothesis_verdict": preliminary_verdict,
        "primary_support_threshold": {
            "minimum_dev_matched_pairs": 100,
            "minimum_primary_risk_difference": 0.05,
            "required_positive_directional_uplift_horizons_minutes": [5, 10, 15],
        },
        "secondary_horizons_minutes": list(HORIZONS),
        "claim_boundary": {
            "strategy_tested": False,
            "option_data_used": False,
            "paper_eligibility": False,
            "live_eligibility": False,
            "robust_support_possible_from_this_run": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--partition", choices=("DEV",), default="DEV")
    parser.add_argument(
        "--known-partial-corpus",
        action="store_true",
        help="Bind input to the certified NSE_FO_61093 LFS object and DEV-only identity.",
    )
    args = parser.parse_args()
    report = run(
        args.input,
        expected_sha256=args.expected_sha256,
        partition=args.partition,
        known_partial_corpus=args.known_partial_corpus,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

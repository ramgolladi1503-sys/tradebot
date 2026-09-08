from __future__ import annotations

import hashlib
import json
from typing import Iterable

import pandas as pd


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_chronological_split_manifest(session_dates: Iterable[object]) -> dict[str, object]:
    dates = sorted(
        {
            pd.Timestamp(value).date().isoformat()
            for value in session_dates
            if value is not None and not pd.isna(value)
        }
    )
    count = len(dates)
    if count == 0:
        development: list[str] = []
        validation: list[str] = []
        holdout: list[str] = []
        coverage = "NO_SESSIONS"
    elif count < 3:
        development = list(dates)
        validation = []
        holdout = []
        coverage = "SMOKE_ONLY"
    else:
        development_count = max(1, int(count * 0.60))
        validation_count = max(1, int(count * 0.20))
        if development_count + validation_count >= count:
            validation_count = 1
            development_count = max(1, count - 2)
        holdout_count = count - development_count - validation_count
        if holdout_count <= 0:
            holdout_count = 1
            development_count = max(1, development_count - 1)

        development = dates[:development_count]
        validation = dates[development_count : development_count + validation_count]
        holdout = dates[development_count + validation_count :]

        span_days = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days
        if (
            count >= 100
            and len(validation) >= 20
            and len(holdout) >= 20
            and span_days >= 180
        ):
            coverage = "DEVELOPMENT_VALIDATION_HOLDOUT_READY"
        elif count >= 30 and validation and holdout:
            coverage = "DEVELOPMENT_VALIDATION_ONLY"
        else:
            coverage = "SMOKE_ONLY"

    partitions = {
        "development": development,
        "validation": validation,
        "holdout": holdout,
    }
    manifest = {
        "schema_version": "compression_breakout_split_manifest_v1",
        "partition_policy": "chronological_60_20_20_no_outcome_selection",
        "session_count": count,
        "session_start": dates[0] if dates else None,
        "session_end": dates[-1] if dates else None,
        "partitions": partitions,
        "partition_hashes": {
            name: _canonical_hash(values)
            for name, values in partitions.items()
        },
        "coverage_verdict": coverage,
        "holdout_sealed": True,
        "holdout_outcomes_read": False,
        "allowed_for_live_execution": False,
    }
    manifest["manifest_hash"] = _canonical_hash(manifest)
    return manifest

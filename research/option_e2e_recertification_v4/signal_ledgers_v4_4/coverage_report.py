from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .source_registry import SourceRecord


def build_coverage_report(records: list[SourceRecord]) -> dict[str, Any]:
    return {
        "resolved": sum(1 for record in records if record.resolution_status == "SIGNAL_SOURCE_RESOLVED"),
        "blocked": sum(1 for record in records if record.resolution_status != "SIGNAL_SOURCE_RESOLVED"),
        "blocker_codes": sorted({record.blocker_code for record in records if record.blocker_code}),
        "records": [asdict(record) for record in records],
    }

from __future__ import annotations

from typing import Any

import pandas as pd

from .calibration import PSILORError


_STAGES = (
    "market_opportunity",
    "event_location_correct",
    "direction_correct",
    "contract_correct",
    "exit_positive",
    "implementable_positive",
)


def build_oracle_ladder(frame: pd.DataFrame) -> dict[str, Any]:
    missing = [column for column in _STAGES if column not in frame]
    if missing:
        raise PSILORError(f"oracle frame missing columns: {missing}")
    counts: dict[str, int] = {}
    current = pd.Series(True, index=frame.index)
    previous_count = int(current.sum())
    for stage in _STAGES:
        stage_values = frame[stage].fillna(False).astype(bool)
        current = current & stage_values
        count = int(current.sum())
        if count > previous_count:
            raise PSILORError("oracle ladder counts cannot increase")
        counts[stage] = count
        previous_count = count
    return {
        "rows": int(len(frame)),
        "stage_counts": counts,
        "implementable_positive_rate": (
            counts["implementable_positive"] / len(frame)
            if len(frame)
            else None
        ),
        "read_only": True,
        "allowed_for_live_execution": False,
    }

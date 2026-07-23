from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class WFAPartition:
    development_start: str
    development_end: str
    validation_start: str
    validation_end: str
    holdout_start: str
    holdout_end: str
    holdout_opened: bool = False

    def validate_before_selection_freeze(self) -> None:
        dates = [
            pd.Timestamp(self.development_start),
            pd.Timestamp(self.development_end),
            pd.Timestamp(self.validation_start),
            pd.Timestamp(self.validation_end),
            pd.Timestamp(self.holdout_start),
            pd.Timestamp(self.holdout_end),
        ]
        if not all(left < right for left, right in zip(dates, dates[1:])):
            raise ValueError("wfa_partition_not_chronological")
        if self.holdout_opened:
            raise ValueError("holdout_loaded_before_selection_freeze")

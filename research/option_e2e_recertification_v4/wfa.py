from __future__ import annotations

from dataclasses import dataclass


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
        if not (
            self.development_start
            < self.development_end
            < self.validation_start
            < self.validation_end
            < self.holdout_start
            < self.holdout_end
        ):
            raise ValueError("wfa_partition_not_chronological")
        if self.holdout_opened:
            raise ValueError("holdout_loaded_before_selection_freeze")

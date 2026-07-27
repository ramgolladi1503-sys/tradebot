from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FilenameEvidence:
    observed_filename_identity: bool
    filename_symbol: str
    filename_option_right: str
    filename_strike: str
    filename_expiry: str


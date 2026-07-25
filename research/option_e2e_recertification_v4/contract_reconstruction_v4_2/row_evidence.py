from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RowEvidence:
    observed_row_identity: bool
    observed_token: str
    observed_underlying: str
    observed_option_right: str
    observed_strike: str
    observed_expiry: str
    observed_bid_ask: bool
    observed_quote_timestamp: str


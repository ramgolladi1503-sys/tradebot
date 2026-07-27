from __future__ import annotations

from .composite_contract_authority import QuoteContractEvidence


def assert_no_conflicting_identity(rows: tuple[QuoteContractEvidence, ...]) -> None:
    seen: dict[tuple[str, str], QuoteContractEvidence] = {}
    for row in rows:
        key = (row.trading_symbol, row.instrument_token)
        existing = seen.get(key)
        if existing is None:
            seen[key] = row
            continue
        if (
            existing.expiry != row.expiry
            or existing.strike != row.strike
            or existing.option_right != row.option_right
            or existing.underlying != row.underlying
        ):
            raise ValueError("duplicate_conflicting_contract_identity")

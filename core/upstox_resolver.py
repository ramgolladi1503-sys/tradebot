"""Resolve Upstox instrument keys for option contracts.

Backward-compatible wrapper around core.upstox_instruments.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.upstox_instruments import resolve_upstox_key as _resolve_upstox_key


def resolve_upstox_key(row: dict, instruments_path: Path | None = None) -> str | None:
    return _resolve_upstox_key(row, instruments_path=instruments_path)


def ensure_upstox_columns(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return df
    for col in (
        "upstox_instrument_key",
        "upstox_contract_url",
        "upstox_search_url",
        "upstox_query",
        "unresolved_contract",
    ):
        if col not in df.columns:
            df[col] = None
    return df

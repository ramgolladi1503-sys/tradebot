from __future__ import annotations

from typing import Mapping, Sequence

import pandas as pd

from . import benchmark as B


def efficient_add_split(
    data: pd.DataFrame,
    splits_by_symbol: Mapping[str, Mapping[str, Sequence[str]]],
) -> pd.DataFrame:
    """Equivalent split labeling without rebuilding date sets per row."""
    lookup: dict[tuple[str, str], str] = {}
    for symbol, splits in splits_by_symbol.items():
        for split, dates in splits.items():
            for session_date in dates:
                lookup[(str(symbol), str(session_date))] = str(split)

    out = data.copy()
    out["split"] = [
        lookup.get((str(symbol), str(session_date)), "excluded")
        for symbol, session_date in out[["symbol", "session_date"]].itertuples(
            index=False, name=None
        )
    ]
    return out


def install() -> None:
    B.add_split = efficient_add_split

#!/usr/bin/env python3
from __future__ import annotations

from pathlib import PurePosixPath
import re

import run_tracked_archive_compression_smoke as smoke_v1


smoke_v1._OPTION_RE = re.compile(
    r"(?P<underlying>BANKNIFTY|NIFTY|SENSEX)"
    r"[ _-]+(?P<strike>\d{4,6}(?:\.\d+)?)"
    r"[ _-]+(?P<option_type>CE|PE)"
    r"[ _-]+(?P<expiry>\d{1,2}[ _-]+[A-Z]{3}[ _-]+\d{2})$",
    re.IGNORECASE,
)


def _select_underlying_member(members: list[str]) -> str:
    preferred = (
        "upstox_candidate_replay/20260709/underlying/"
        "NSE_INDEX|Nifty 50_20260709.parquet",
        "upstox_candidate_replay/20260709/underlying/NIFTY 50.parquet",
    )
    for member in preferred:
        if member in members:
            return member

    candidates: list[str] = []
    for member in members:
        path = PurePosixPath(member)
        stem = path.stem.upper()
        if smoke_v1.SESSION_DIRECTORY not in path.parts:
            continue
        if path.suffix.lower() != ".parquet":
            continue
        if "NIFTY" not in stem or "BANKNIFTY" in stem:
            continue
        if re.search(r"(?:^|[ _-])(CE|PE)(?:$|[ _-])", stem):
            continue
        if "NSE_INDEX" in stem or stem in {"NIFTY 50", "NIFTY"}:
            candidates.append(member)

    if len(candidates) != 1:
        raise ValueError(
            f"underlying_member_not_unique:{len(candidates)}:{candidates[:10]}"
        )
    return candidates[0]


smoke_v1._select_underlying_member = _select_underlying_member


if __name__ == "__main__":
    raise SystemExit(smoke_v1.main())

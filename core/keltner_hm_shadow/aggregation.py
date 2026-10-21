from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass(frozen=True)
class Bar:
    symbol: str
    start: datetime
    completion: datetime
    open: float
    high: float
    low: float
    close: float
    session_id: str
    source: str = "unknown"
    sequence: int | None = None

def aggregate_complete(bars: list[Bar], group_size: int) -> list[Bar]:
    if group_size <= 0:
        raise ValueError("group_size")
    out: list[Bar] = []
    by_key: dict[tuple[str, str], list[Bar]] = {}
    for bar in sorted(bars, key=lambda b: (b.session_id, b.symbol, b.start)):
        by_key.setdefault((bar.session_id, bar.symbol), []).append(bar)
    for (session_id, symbol), rows in by_key.items():
        for i in range(0, len(rows), group_size):
            chunk = rows[i:i + group_size]
            if len(chunk) != group_size:
                continue
            expected = [chunk[0].start + timedelta(minutes=5 * j) for j in range(group_size)]
            if [b.start for b in chunk] != expected:
                continue
            out.append(Bar(symbol=symbol, start=chunk[0].start, completion=chunk[-1].completion,
                open=chunk[0].open, high=max(b.high for b in chunk), low=min(b.low for b in chunk),
                close=chunk[-1].close, session_id=session_id, source=chunk[0].source,
                sequence=chunk[-1].sequence))
    return out

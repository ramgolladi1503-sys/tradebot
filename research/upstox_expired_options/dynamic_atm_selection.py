from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

import pandas as pd

IST = 'Asia/Kolkata'


def round_atm(price: float, step: float = 50.0) -> float:
    return float(
        (Decimal(str(float(price))) / Decimal(str(step))).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP
        )
        * Decimal(str(step))
    )


def dynamic_cycle_strike_union(
    underlying: pd.DataFrame,
    available_strikes: Iterable[float],
    expiry: date,
    *,
    cycle_days: int = 7,
    wings: int = 2,
) -> tuple[float, ...]:
    """Return the union of ATM strike wings for every session in the expiry cycle."""

    if wings < 0:
        raise ValueError('wings_must_be_non_negative')
    strikes = sorted({float(value) for value in available_strikes})
    if not strikes:
        return ()

    rows = underlying.copy()
    stamps = pd.to_datetime(rows['timestamp'])
    if stamps.dt.tz is None:
        stamps = stamps.dt.tz_localize('UTC')
    rows['timestamp'] = stamps.dt.tz_convert(IST)
    rows['session_date'] = rows['timestamp'].dt.date
    start = expiry - timedelta(days=cycle_days)
    rows = rows[
        (rows.session_date >= start) & (rows.session_date <= expiry)
    ].sort_values('timestamp')
    session_opens = rows.groupby('session_date', sort=True).first()['open']

    selected: set[float] = set()
    for spot in session_opens:
        centre = min(
            range(len(strikes)),
            key=lambda index: (abs(strikes[index] - float(spot)), strikes[index]),
        )
        selected.update(
            strikes[
                max(0, centre - wings) : min(len(strikes), centre + wings + 1)
            ]
        )
    return tuple(sorted(selected))

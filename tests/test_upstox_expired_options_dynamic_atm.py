from datetime import date

import pandas as pd

from research.upstox_expired_options.dynamic_atm_selection import (
    dynamic_cycle_strike_union,
)


def test_dynamic_union_covers_each_session_atm_band():
    frame = pd.DataFrame(
        {
            'timestamp': [
                '2025-01-01T03:45:00Z',
                '2025-01-02T03:45:00Z',
            ],
            'open': [24000, 25000],
        }
    )
    strikes = list(range(23800, 25201, 50))
    selected = dynamic_cycle_strike_union(
        frame,
        strikes,
        date(2025, 1, 2),
        cycle_days=7,
        wings=2,
    )
    assert {23900, 23950, 24000, 24050, 24100}.issubset(selected)
    assert {24900, 24950, 25000, 25050, 25100}.issubset(selected)
    assert len(selected) == 10

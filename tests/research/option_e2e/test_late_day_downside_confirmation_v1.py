import json
from pathlib import Path

import pandas as pd
import pytest

from research.option_e2e_recertification_v4.late_day_downside_confirmation_v1.engine import (
    Policy,
    causal_confirmation,
    replay_one,
    round_atm,
)


def test_round_atm_half_up():
    assert round_atm(24225) == 24250
    assert round_atm(24224.9) == 24200


def test_confirmation_uses_only_completed_bars():
    rows = []
    for minute, close in [(0, 100), (5, 110), (6, 500)]:
        rows.append(
            {
                'timestamp': pd.Timestamp(
                    f'2025-01-01 14:{minute:02d}', tz='Asia/Kolkata'
                ),
                'close': close,
                'volume': 1,
                'open_interest': 1,
            }
        )
    out = causal_confirmation(
        rows,
        pd.Timestamp('2025-01-01 14:06', tz='Asia/Kolkata'),
        5,
    )
    assert out['premium_change_pct'] == pytest.approx(10.0)
    assert out['last_completed_timestamp'].minute == 5


def test_replay_requires_positive_confirmation_and_next_bar(tmp_path: Path):
    candles = []
    for minute, close in [(0, 100), (5, 110), (6, 111), (7, 120), (26, 130)]:
        candles.append(
            [
                f'2025-01-01T14:{minute:02d}:00+05:30',
                close,
                close,
                close,
                close,
                100,
                1000,
            ]
        )
    path = tmp_path / 'candles.json'
    path.write_text(json.dumps({'data': {'candles': candles}}))
    intent = {
        'signal_timestamp': '2025-01-01T14:06:00+05:30',
        'underlying_price': 24224,
        'partition': 'development',
        'signal_identity_hash': 'x',
    }
    contract = {
        'path': str(path),
        'expiry': pd.Timestamp('2025-01-02').date(),
        'strike': 24200,
    }
    out = replay_one(intent, contract, Policy())
    assert out is not None
    assert out['entry_timestamp'].endswith('14:07:00+05:30')
    assert out['premium_change_pct'] > 0

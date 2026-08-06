from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import importlib.util
import sys

import numpy as np
import pandas as pd
import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts'
    / 'run_observation_first_pattern_atlas_motifs_v1.py'
)
SPEC = importlib.util.spec_from_file_location('atlas_motifs_v1', MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def make_session(session_date: date, pattern: int, regime: str = 'PRE_CAS') -> pd.DataFrame:
    points = 76 if regime == 'PRE_CAS' else 78
    start = pd.Timestamp.combine(session_date, pd.Timestamp('09:15').time()).tz_localize('Asia/Kolkata')
    timestamps = pd.date_range(start, periods=points, freq='5min')
    x = np.linspace(0, 1, points)
    if pattern == 0:
        path = 0.006 * x + 0.0005 * np.sin(6 * np.pi * x)
    elif pattern == 1:
        path = -0.005 * x + 0.0004 * np.sin(5 * np.pi * x)
    else:
        path = 0.002 * np.sin(4 * np.pi * x)
    prices = 22000 * np.exp(path)
    vwap = pd.Series(prices).expanding().mean().to_numpy()
    return pd.DataFrame({
        'timestamp': timestamps,
        'instrument': 'NIFTY',
        'session_date': session_date,
        'regime': regime,
        'price': prices,
        'volume': 0.0,
        'causal_vwap': vwap,
        'session_progress': np.linspace(0, 1, points),
        'observed_this_minute': True,
    })


def make_corpus(session_count: int = 150) -> pd.DataFrame:
    start = date(2024, 1, 1)
    sessions = []
    current = start
    while len(sessions) < session_count:
        if current.weekday() < 5:
            sessions.append(make_session(current, len(sessions) % 3))
        current += timedelta(days=1)
    return pd.concat(sessions, ignore_index=True)


def test_outcome_columns_fail_closed() -> None:
    frame = make_session(date(2024, 1, 2), 0)
    frame['future_return_15'] = 0.01
    with pytest.raises(ValueError, match='Outcome-like columns'):
        MODULE.prepare_native_rows(frame)


def test_windows_do_not_cross_sessions_and_use_native_cadence() -> None:
    frame = MODULE.prepare_native_rows(pd.concat([
        make_session(date(2024, 1, 2), 0),
        make_session(date(2024, 1, 3), 1),
    ], ignore_index=True))
    values, metadata = MODULE.build_windows(frame, 15, 5.0, max_windows_per_session=None)
    assert values.shape[0] == 2 * (((76 - 4) // 2) + 1)
    assert set(metadata['points']) == {4}
    assert set(metadata['stride_points']) == {2}
    assert all(
        pd.Timestamp(row.start_timestamp).date() == pd.Timestamp(row.end_timestamp).date()
        for row in metadata.itertuples()
    )


def test_chronological_split_preserves_unopened_tail() -> None:
    sessions = [f'2024-01-{day:02d}' for day in range(1, 31)]
    split = MODULE.chronological_split(sessions, minimum_unopened=5)
    assert split.observation[0] == '2024-01-01'
    assert split.unopened[-1] == '2024-01-30'
    assert set(split.observation).isdisjoint(split.replication)
    assert set(split.observation).isdisjoint(split.unopened)
    assert set(split.replication).isdisjoint(split.unopened)
    assert len(split.unopened) >= 5


def test_insufficient_post_cas_lane_fails_without_model() -> None:
    frames = [
        make_session(date(2026, 8, 3) + timedelta(days=index), index % 3, 'POST_CAS')
        for index in range(8)
    ]
    native = MODULE.prepare_native_rows(pd.concat(frames, ignore_index=True))
    result = MODULE.run_lane(native, 'NIFTY', 'POST_CAS', minimum_sessions=20)
    assert result['verdict'] == 'INSUFFICIENT_SESSIONS_FOR_MOTIF_DISCOVERY'
    assert result['windows'] == []


def test_repeating_synthetic_shapes_freeze_replication_stable_motifs() -> None:
    native = MODULE.prepare_native_rows(make_corpus(120))
    result = MODULE.run_lane(
        native,
        'NIFTY',
        'PRE_CAS',
        minimum_sessions=100,
        windows=(15,),
        minimum_clusters=3,
        maximum_clusters=4,
        max_windows_per_session=20,
    )
    assert result['unopened_sessions_scored'] is False
    assert len(result['unopened_sessions']) >= 10
    assert result['verdict'] == 'OUTCOME_BLIND_NATIVE_CADENCE_MOTIFS_FROZEN'
    assert result['frozen_motif_count'] > 0
    assert {item['window_minutes'] for item in result['windows']} == {15}
    assert any(item.get('motifs') for item in result['windows'])

import pytest
import pandas as pd
import numpy as np
from research.opening_state_momentum.timestamp_normalization import normalize_timestamps

def test_naive_timestamp_localization_asia_kolkata():
    s = pd.Series([pd.Timestamp('2024-10-14 14:45:00')])
    res = normalize_timestamps(s)
    assert res.dt.tz is not None
    assert str(res.dt.tz) == 'Asia/Kolkata'

def test_aware_timestamp_conversion_asia_kolkata():
    s = pd.Series([pd.Timestamp('2024-10-14 09:15:00', tz='UTC')])
    res = normalize_timestamps(s)
    assert str(res.dt.tz) == 'Asia/Kolkata'
    assert res.iloc[0].hour == 14
    assert res.iloc[0].minute == 45

def test_naive_timestamp_is_not_interpreted_as_utc():
    s = pd.Series([pd.Timestamp('2024-10-14 14:45:00')])
    res = normalize_timestamps(s)
    # If it was interpreted as UTC and converted to Asia/Kolkata, the hour would be 20:15
    assert res.iloc[0].hour == 14
    assert res.iloc[0].minute == 45

def test_mixed_timezone_input_fails():
    s = pd.Series([
        pd.Timestamp('2024-10-14 14:45:00'),
        pd.Timestamp('2024-10-14 14:46:00', tz='Asia/Kolkata')
    ])
    with pytest.raises(ValueError, match="Mixed aware/naive values|Unparsable"):
        normalize_timestamps(s)

def test_unparsable_timestamp_fails():
    s = pd.Series(["not_a_time", "2024-10-14"])
    with pytest.raises(ValueError):
        normalize_timestamps(s)

def test_duplicate_normalized_timestamp_fails():
    s = pd.Series([
        pd.Timestamp('2024-10-14 14:45:00'),
        pd.Timestamp('2024-10-14 14:45:00')
    ])
    with pytest.raises(ValueError, match="Duplicate normalized timestamps"):
        normalize_timestamps(s)

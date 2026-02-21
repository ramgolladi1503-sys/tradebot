from core.time_utils import compute_age_sec


def test_compute_age_sec_seconds_domain():
    assert compute_age_sec(1000.0, 1012.5) == 12.5


def test_compute_age_sec_millis_normalized_and_non_negative():
    # Future timestamp should clamp to 0.0 after normalization.
    assert compute_age_sec(1_700_000_100_000, 1_700_000_000_000) == 0.0


def test_compute_age_sec_invalid_returns_none():
    assert compute_age_sec(None, 1000.0) is None
    assert compute_age_sec(1000.0, None) is None

from core.market_data import _indicator_freshness_status


def test_indicator_freshness_fresh_update_age_near_zero():
    out = _indicator_freshness_status(
        required_inputs_ok=True,
        last_update_epoch=1000.0,
        stale_sec=120.0,
        now_epoch=1000.4,
    )
    assert out["ok"] is True
    assert out["stale"] is False
    assert 0.0 <= out["age_sec"] <= 1.0


def test_indicator_freshness_stale_after_threshold():
    out = _indicator_freshness_status(
        required_inputs_ok=True,
        last_update_epoch=700.0,
        stale_sec=120.0,
        now_epoch=1000.0,
    )
    assert out["ok"] is False
    assert out["stale"] is True
    assert out["age_sec"] == 300.0


def test_indicator_freshness_resets_on_new_update():
    stale = _indicator_freshness_status(
        required_inputs_ok=True,
        last_update_epoch=700.0,
        stale_sec=120.0,
        now_epoch=1000.0,
    )
    fresh = _indicator_freshness_status(
        required_inputs_ok=True,
        last_update_epoch=999.8,
        stale_sec=120.0,
        now_epoch=1000.0,
    )
    assert stale["stale"] is True
    assert fresh["stale"] is False
    assert fresh["ok"] is True


def test_indicator_freshness_never_computed_uses_huge_age_and_reason():
    out = _indicator_freshness_status(
        required_inputs_ok=False,
        last_update_epoch=None,
        stale_sec=120.0,
        now_epoch=1000.0,
        never_computed_age_sec=1e9,
    )
    assert out["ok"] is False
    assert out["stale"] is True
    assert out["age_sec"] >= 1e9
    assert out["reason"] == "indicators_never_computed"

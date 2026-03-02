from config import profile


def test_option_filter_profile_switching_deterministic(monkeypatch):
    monkeypatch.setattr(profile.cfg, "PAPER_RELAXED_SPREAD_MULT", 1.30, raising=False)
    monkeypatch.setattr(profile.cfg, "PAPER_RELAXED_MIN_VOLUME_MULT", 0.50, raising=False)
    monkeypatch.setattr(profile.cfg, "PAPER_RELAXED_PREMIUM_RELAX_PCT", 0.25, raising=False)

    live = profile.get_option_filter_profile(
        mode="LIVE",
        base_max_spread_pct=0.03,
        base_min_volume_filter=500,
    )
    paper = profile.get_option_filter_profile(
        mode="PAPER",
        base_max_spread_pct=0.03,
        base_min_volume_filter=500,
    )

    assert live.name == "LIVE_STRICT"
    assert live.max_spread_pct == 0.03
    assert live.min_volume_filter == 500
    assert live.premium_relax_pct == 0.0

    assert paper.name == "PAPER_RELAXED"
    assert paper.max_spread_pct == 0.039
    assert paper.min_volume_filter == 250
    assert paper.premium_relax_pct == 0.25

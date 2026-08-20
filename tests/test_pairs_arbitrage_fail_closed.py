from strategies.pairs_arbitrage import generate_signal


def test_pairs_arbitrage_fails_closed_on_weak_stationarity():
    debug = {}
    assert (
        generate_signal(
            100.0,
            99.0,
            historical_a=[100.0] * 10,
            historical_b=[99.0] * 10,
            debug_stats=debug,
            regime="UNKNOWN",
            leg_a_age_sec=0.5,
            leg_b_age_sec=0.5,
            max_leg_age_sec=5.0,
            cross_asset_health=True,
        )
        is None
    )
    assert debug["candidates_rejected_pre_score"] == 1
    assert debug["rejection_reason_counts"]["invalid_spread_truth"] == 1

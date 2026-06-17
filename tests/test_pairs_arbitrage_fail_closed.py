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
        )
        is None
    )
    assert debug["candidates_rejected_pre_score"] == 1
    assert debug["rejection_reason_counts"]["half_life_too_long"] == 1

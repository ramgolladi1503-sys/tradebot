from core.blocker_lifecycle import evaluate_feed_symbol_blockers, BlockerRegistry
registry = BlockerRegistry("test")
evaluate_feed_symbol_blockers(
    registry=registry,
    now_ts=105.0,
    symbol="NIFTY",
    ws_connected=True,
    expected_option_count=1,
    subscribed_option_count=1,
    option_ticks_received_count=0,
    latest_option_tick_ts=None,
    latest_option_tick_age_sec=None,
    feed_freshness_sec=2.0,
    min_required_count=1,
)
for k, v in registry._records.items():
    print(k, v.active)

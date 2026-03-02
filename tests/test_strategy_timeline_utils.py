import pandas as pd

from dashboard.ui.utils.strategy_timeline import (
    compute_strategy_timeline_metrics,
    floor_timestamp_to_bucket,
)


def test_time_bucket_flooring():
    ts = "2026-02-27T10:07:31+05:30"
    bucket = floor_timestamp_to_bucket(ts, "5m")
    assert bucket == pd.Timestamp("2026-02-27T04:35:00+00:00")


def test_metrics_computation_demoted_rate():
    df = pd.DataFrame(
        [
            {
                "ts_sort": "2026-02-27T04:36:10+00:00",
                "strategy_family": "STRAT_A",
                "permission_bucket": "HIGH_EXECUTE",
                "final_action": "ADVISORY_ONLY",
                "final_blocker": "stale_option_ltp",
            },
            {
                "ts_sort": "2026-02-27T04:36:25+00:00",
                "strategy_family": "STRAT_A",
                "permission_bucket": "HIGH_EXECUTE",
                "final_action": "EXECUTE",
                "final_blocker": "none",
            },
            {
                "ts_sort": "2026-02-27T04:36:40+00:00",
                "strategy_family": "STRAT_A",
                "permission_bucket": "QUEUE",
                "final_action": "ADVISORY_ONLY",
                "final_blocker": "stale_option_ltp",
            },
        ]
    )

    out = compute_strategy_timeline_metrics(df, bucket_size="1m", ts_col="ts_sort")
    row = out.iloc[0]
    assert int(row["candidates"]) == 3
    assert int(row["high_execute"]) == 2
    assert int(row["executed"]) == 1
    assert int(row["demoted"]) == 1
    assert float(row["demoted_rate"]) == 0.5
    assert round(float(row["execution_rate"]), 4) == round(1 / 3, 4)
    assert str(row["top_blocker"]) == "stale_option_ltp"

import pandas as pd

from dashboard.ui.utils.strategy_timeline import (
    compute_strategy_timeline_metrics,
    floor_timestamp_to_bucket,
    build_blocker_distribution,
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


def test_build_blocker_distribution_has_stable_columns():
    df = pd.DataFrame(
        [
            {"final_blocker": "no_signal"},
            {"final_blocker": "no_signal"},
            {"final_blocker": "premium_band_fail"},
            {"final_blocker": None},
        ]
    )
    out = build_blocker_distribution(df, blocker_col="final_blocker")
    assert list(out.columns) == ["final_blocker", "count"]
    assert out["final_blocker"].tolist()[0] == "no_signal"
    assert int(out.loc[out["final_blocker"] == "no_signal", "count"].iloc[0]) == 2
    assert int(out.loc[out["final_blocker"] == "NONE", "count"].iloc[0]) == 1

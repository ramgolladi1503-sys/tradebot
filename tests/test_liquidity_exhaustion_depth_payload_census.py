from __future__ import annotations

import pandas as pd

from research.liquidity_exhaustion_depth_schema_v2.payload_census import census_depth_series


def test_exact_census_detects_fully_empty_depth_sequences() -> None:
    result = census_depth_series(pd.Series([{"bids": [], "asks": []}] * 3))
    assert result["row_count"] == 3
    assert result["mapping_rows"] == 3
    assert result["rows_with_nonempty_bids"] == 0
    assert result["rows_with_nonempty_asks"] == 0
    assert result["all_depth_sequences_empty"] is True


def test_exact_census_counts_nonempty_entries_and_signatures() -> None:
    result = census_depth_series(
        pd.Series(
            [
                {"bids": [{"price": 100.0, "quantity": 10}], "asks": []},
                {
                    "bids": [{"price": 99.5, "quantity": 12}],
                    "asks": [{"price": 100.5, "quantity": 8}],
                },
            ]
        )
    )
    assert result["rows_with_nonempty_bids"] == 2
    assert result["rows_with_nonempty_asks"] == 1
    assert result["rows_with_both_sides"] == 1
    assert result["total_bid_entries"] == 2
    assert result["total_ask_entries"] == 1
    assert result["all_depth_sequences_empty"] is False
    assert result["nonempty_examples"]


def test_exact_census_fails_shape_without_inference() -> None:
    result = census_depth_series(pd.Series([{"buy": [], "sell": []}, "bad", None]))
    assert result["null_rows"] == 1
    assert result["malformed_rows"] == 2
    assert result["all_depth_sequences_empty"] is False

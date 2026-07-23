from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.liquidity_exhaustion_depth_schema_v2.schema_probe import (
    collect_path_types,
    deterministic_sample_positions,
    inspect_depth_series,
    normalize_depth_value,
    shape_signature,
)


def test_normalize_depth_value_decodes_json_and_numpy() -> None:
    raw = json.dumps({"buy": [{"price": 100.5, "quantity": 10}]})
    normalized = normalize_depth_value(raw)
    assert normalized == {"buy": [{"price": 100.5, "quantity": 10}]}
    assert normalize_depth_value(np.array([1, 2])) == [1, 2]


def test_shape_signature_is_mapping_order_independent() -> None:
    left = {"sell": [{"quantity": 4, "price": 101}], "buy": [{"price": 100, "quantity": 5}]}
    right = {"buy": [{"quantity": 5, "price": 100}], "sell": [{"price": 101, "quantity": 4}]}
    assert shape_signature(left) == shape_signature(right)


def test_collect_path_types_exposes_nested_price_and_size_paths() -> None:
    value = {"buy": [{"price": 100.0, "quantity": 10}], "sell": [{"price": 101.0, "quantity": 12}]}
    paths = collect_path_types(value)
    assert paths["$.buy[].price|number"] == 1
    assert paths["$.buy[].quantity|number"] == 1
    assert paths["$.sell[].price|number"] == 1


def test_deterministic_sample_positions_cover_boundaries() -> None:
    positions = deterministic_sample_positions(1000, limit=5)
    assert positions[0] == 0
    assert positions[-1] == 999
    assert positions == deterministic_sample_positions(1000, limit=5)


def test_inspect_depth_series_discovers_price_and_size_keys() -> None:
    series = pd.Series(
        [
            {"buy": [{"price": 100.0, "quantity": 10}], "sell": [{"price": 101.0, "quantity": 12}]},
            {"buy": [{"price": 99.5, "quantity": 11}], "sell": [{"price": 100.5, "quantity": 13}]},
        ]
    )
    result = inspect_depth_series(series, sample_limit=2)
    assert result["sample_count"] == 2
    assert "price" in result["price_like_keys"]
    assert "quantity" in result["size_like_keys"]
    assert result["dominant_signature"] is not None

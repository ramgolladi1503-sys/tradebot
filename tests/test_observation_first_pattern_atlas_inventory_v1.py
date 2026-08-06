from __future__ import annotations

from datetime import date
from pathlib import Path
import importlib.util
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_observation_first_pattern_atlas_inventory_v1.py"
SPEC = importlib.util.spec_from_file_location("atlas_inventory", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_outcome_like_columns_are_detected_without_matching_plain_observation_fields() -> None:
    columns = [
        "event_timestamp",
        "open",
        "high",
        "low",
        "close",
        "future_return_15",
        "entry_price",
        "net_pnl",
        "outcome_label",
    ]
    assert MODULE.outcome_like_columns(columns) == [
        "entry_price",
        "future_return_15",
        "net_pnl",
        "outcome_label",
    ]


def test_family_classification_prefers_option_schema() -> None:
    family = MODULE.classify_family(
        Path("warehouse/options/session.parquet"),
        ["event_timestamp", "option_type", "strike", "premium_velocity", "open_interest_sum"],
    )
    assert family == "option"


def test_regime_boundary_is_exact() -> None:
    assert MODULE.CAS_START_DATE == date(2026, 8, 3)
    assert MODULE.regime_for_path("trade_date=2026-08-02/data.parquet") == "PRE_CAS"
    assert MODULE.regime_for_path("trade_date=2026-08-03/data.parquet") == "POST_CAS"
    assert MODULE.regime_for_path("trade_date=20260804/data.parquet") == "POST_CAS"
    assert MODULE.regime_for_path("undated/data.parquet") == "UNRESOLVED"


def test_find_first_preserves_actual_column_name() -> None:
    assert MODULE.find_first(
        ["Session_ID", "Event_Timestamp", "close"],
        MODULE.TIMESTAMP_CANDIDATES,
    ) == "Event_Timestamp"

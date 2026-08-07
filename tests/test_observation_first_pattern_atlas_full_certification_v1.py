from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_observation_first_pattern_atlas_full_certification_v1.py"
)
SPEC = importlib.util.spec_from_file_location("atlas_full_certification", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_bh_qvalues_preserve_original_order_and_bounds() -> None:
    q = MODULE.bh_qvalues([0.01, 0.20, 0.03])
    assert q == pytest.approx([0.03, 0.20, 0.045])
    assert all(0.0 <= value <= 1.0 for value in q)
    assert q[0] <= q[2] <= q[1]


def test_mechanism_classifies_continuation_and_reversal() -> None:
    continuation = {
        "median_prefix_log_return": 0.001,
        "median_completion_log_return": 0.002,
        "median_prefix_amplitude": 0.002,
    }
    reversal = {
        "median_prefix_log_return": 0.001,
        "median_completion_log_return": -0.002,
        "median_prefix_amplitude": 0.002,
    }
    assert MODULE.mechanism_type(continuation) == "PERSISTENT_EXPANSION_CONTINUATION"
    assert MODULE.mechanism_type(reversal) == "FAILED_EXPANSION_REVERSAL"


def test_summarize_excess_uses_session_level_events() -> None:
    events = [
        {"directional_excess_bps": 4.0},
        {"directional_excess_bps": 3.0},
        {"directional_excess_bps": -1.0},
    ]
    result = MODULE.summarize_excess(events)
    assert result["n"] == 3
    assert result["hit_rate"] == 2 / 3
    assert result["mean_excess_bps"] == 2.0


def test_structural_screen_can_pass_strong_fixed_evidence() -> None:
    record = {
        "hypothesis": {"hypothesis_id": "H1", "motif_id": "M1"},
        "observation": {
            "n": 30,
            "mean_excess_bps": 5.0,
            "median_excess_bps": 4.0,
            "hit_rate": 0.60,
            "mean_ci90": [2.0, 8.0],
            "one_sided_sign_p": 0.01,
        },
        "replication": {
            "n": 20,
            "mean_excess_bps": 4.0,
            "median_excess_bps": 3.0,
            "hit_rate": 0.60,
            "mean_ci90": [1.0, 7.0],
            "one_sided_sign_p": 0.02,
            "bh_q": 0.05,
        },
        "events": [],
    }
    result = MODULE.structural_screen({"records": [record]})
    assert result["survivor_count"] == 1
    assert result["survivor_hypothesis_ids"] == ["H1"]


def test_structural_screen_rejects_small_replication() -> None:
    record = {
        "hypothesis": {"hypothesis_id": "H1", "motif_id": "M1"},
        "observation": {
            "n": 30,
            "mean_excess_bps": 5.0,
            "median_excess_bps": 4.0,
            "hit_rate": 0.60,
            "mean_ci90": [2.0, 8.0],
            "one_sided_sign_p": 0.01,
        },
        "replication": {
            "n": 5,
            "mean_excess_bps": 8.0,
            "median_excess_bps": 8.0,
            "hit_rate": 0.80,
            "mean_ci90": [3.0, 12.0],
            "one_sided_sign_p": 0.01,
            "bh_q": 0.02,
        },
        "events": [],
    }
    result = MODULE.structural_screen({"records": [record]})
    assert result["survivor_count"] == 0
    assert result["survivor_hypothesis_ids"] == []


def test_strategy_construction_excludes_sub_10_minute_horizon() -> None:
    outcomes = {
        "records": [
            {
                "hypothesis": {
                    "hypothesis_id": "H1",
                    "motif_id": "M1",
                    "primary_horizon_minutes": 5,
                    "expected_completion_sign": 1,
                    "post_cas_revalidation_required": False,
                },
                "events": [],
            }
        ]
    }
    screen = {"survivor_hypothesis_ids": ["H1"]}
    result = MODULE.construct_strategies(outcomes, screen)
    assert result["strategy_count"] == 0
    assert result["survivor_count"] == 0


def test_concentration_ratio_detects_single_trade_dominance() -> None:
    values = np.asarray([100.0, 1.0, 1.0, 1.0, 1.0, -2.0])
    assert MODULE.concentration_ratio(values, top_n=1) > 0.90


def test_walk_forward_rejects_insufficient_dates() -> None:
    trades = [
        {"session_date": f"2024-01-{day:02d}", "net_proxy_bps": 2.0}
        for day in range(1, 11)
    ]
    catalog = {
        "survivor_strategy_ids": ["S1"],
        "trade_book": {"S1": trades},
    }
    result = MODULE.walk_forward(catalog)
    assert result["survivor_strategy_ids"] == []


def test_final_unopened_stays_sealed_without_robust_survivor() -> None:
    result = MODULE.final_unopened_test(
        {"survivor_strategy_ids": []},
        {},
        {},
        {},
        {},
        {},
    )
    assert result["principal_verdict"] == "UNOPENED_NOT_ACCESSED_NO_ROBUST_SURVIVOR"
    assert result["unopened_sessions_scored"] is False


def test_option_translation_blocks_without_contemporaneous_data(tmp_path: Path) -> None:
    result = MODULE.inspect_option_data([tmp_path], {"2024-01-02"})
    assert result["translation_authorized"] is False
    assert result["principal_verdict"] == "OPTION_TRANSLATION_BLOCKED_BY_CERTIFIED_CONTEMPORANEOUS_DATA"


def test_shadow_gate_blocks_without_post_cas_or_option_authority() -> None:
    import pandas as pd

    native = pd.DataFrame(
        {
            "regime": ["PRE_CAS", "PRE_CAS"],
            "session_date": ["2024-01-01", "2024-01-02"],
        }
    )
    result = MODULE.shadow_gate(
        {"survivor_strategy_ids": ["S1"]},
        {"translation_authorized": False},
        native,
    )
    assert result["shadow_authorized"] is False
    assert "option_translation_not_certified" in result["blocking_reasons"]
    assert "post_cas_revalidation_sample_insufficient" in result["blocking_reasons"]


def test_empty_pvalues_have_empty_qvalues() -> None:
    assert MODULE.bh_qvalues([]) == []

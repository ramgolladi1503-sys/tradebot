from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from research.kite_five_minute_campaign.common import canonical_hash
from research.kite_five_minute_campaign.v2 import (
    FAMILIES,
    evaluate_trades,
    v2_contract,
    v2_variants,
)


def _positive_trades(contract: dict) -> list[dict]:
    trades = []
    target = contract["variants"][0]["variant_id"]
    neighbor = contract["variants"][1]["variant_id"]
    for variant_id in (target, neighbor):
        for index in range(90):
            month = 1 + (index % 6)
            regime = ("low", "medium", "high")[index % 3]
            trades.append(
                {
                    "session_date": f"2025-{month:02d}-{1 + index % 20:02d}",
                    "mechanism_id": FAMILIES[0],
                    "variant_id": variant_id,
                    "direction": "LONG",
                    "decision_timestamp": "2025-01-01T09:45:00+05:30",
                    "entry_timestamp": "2025-01-01T09:45:00+05:30",
                    "exit_timestamp": "2025-01-01T10:15:00+05:30",
                    "entry_price": 100.0,
                    "exit_price": 100.2,
                    "gross_return_bps": 20.0,
                    "cost_bps": 2.0,
                    "net_return_bps": 18.0 + (index % 5) * 0.1,
                    "features": {},
                    "regime": regime,
                    "source_file_hashes": {},
                }
            )
    return trades


def test_v1_placeholder_status_is_invalidated() -> None:
    status = json.loads(Path("research/kite_five_minute_campaign/evidence/active_campaign_status.json").read_text())
    assert status["status"] == "INVALID_IMPLEMENTATION_PENDING_V2"
    record = json.loads(Path("research/kite_five_minute_campaign/evidence/invalid_v1_placeholder/invalidation_record.json").read_text())
    assert record["status"] == "INVALID_IMPLEMENTATION"
    assert record["candidate_bundle_hash"] is None


def test_v2_variant_matrix_is_exact_and_distinct() -> None:
    variants = v2_variants()
    assert len(variants) == 24
    assert {v["mechanism_id"] for v in variants} == set(FAMILIES)
    assert all(sum(v["mechanism_id"] == family for v in variants) == 6 for family in FAMILIES)
    assert len({json.dumps(v["parameters"], sort_keys=True) for v in variants}) > 6


def test_forward_return_formula_long_and_short() -> None:
    long_gross = ((102 / 100) - 1) * 10000
    short_gross = ((100 / 98) - 1) * 10000
    assert round(long_gross, 6) == 200.0
    assert round(short_gross, 6) == round(204.08163265306143, 6)


def test_synthetic_positive_control_can_pass_all_gates() -> None:
    contract = v2_contract("a" * 64, "b" * 64)
    records = evaluate_trades(_positive_trades(contract), [], contract)
    target = next(r for r in records if r["variant_id"] == contract["variants"][0]["variant_id"])
    assert target["candidate_eligibility"] is True
    assert all(value == "PASS" for value in target["candidate_gates"].values())


def test_synthetic_null_control_has_no_candidate() -> None:
    contract = v2_contract("a" * 64, "b" * 64)
    trades = _positive_trades(contract)
    for index, trade in enumerate(trades):
        trade["net_return_bps"] = -1.0 if index % 2 else 1.0
        trade["gross_return_bps"] = trade["net_return_bps"] + 2.0
    records = evaluate_trades(trades, [], contract)
    assert not any(r["candidate_eligibility"] for r in records)


def test_negative_direction_fixture_reverses_candidate() -> None:
    contract = v2_contract("a" * 64, "b" * 64)
    trades = _positive_trades(contract)
    for trade in trades:
        trade["net_return_bps"] = -abs(trade["net_return_bps"])
        trade["gross_return_bps"] = trade["net_return_bps"] + 2.0
    records = evaluate_trades(trades, [], contract)
    assert not any(r["candidate_eligibility"] for r in records)


def test_real_runner_requires_explicit_outcome_flag() -> None:
    proc = subprocess.run(
        [
            "python",
            "scripts/run_kite_five_minute_campaign.py",
            "--archive",
            "/Users/madhuram/tradebot/runtime/kite_candidate_replay.zip",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
    )
    assert proc.returncode != 0
    assert "refusing real archive outcome run" in proc.stderr


def test_contract_hash_changes_on_threshold_mutation() -> None:
    contract = v2_contract("a" * 64, "b" * 64)
    mutated = json.loads(json.dumps(contract))
    mutated["variants"][0]["parameters"]["dislocation_threshold"] = 999
    assert canonical_hash(contract) != canonical_hash(mutated)

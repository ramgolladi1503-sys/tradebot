from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.structural_edge_campaign import CampaignContract
from research.structural_edge_campaign.option_repricing_lag import (
    RepricingLagError,
    audit_data_readiness,
    black76_greeks,
    black76_price,
    development_evidence_from_readiness,
    evaluate_repricing_snapshot,
    implied_volatility_black76,
    signal_fingerprint,
)


SPEC_PATH = Path(__file__).resolve().parents[1] / "research/structural_edge_campaign/specs/dorl_v3.json"
SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _snapshot(
    *,
    option_type: str = "CE",
    bearish: bool = False,
    strike_override: float | None = None,
) -> dict:
    previous_futures = 25000.0
    current_futures = 24950.0 if bearish else 25050.0
    strike = (
        strike_override
        if strike_override is not None
        else (25150.0 if bearish else 24850.0)
    )
    years = 3.0 / 365.0
    vol = 0.18
    previous_mid = black76_price(
        option_type,
        previous_futures,
        strike,
        years,
        vol,
        0.065,
    )
    current_mid = previous_mid + 10.0
    return {
        "timestamp": "2026-07-20T10:15:00+05:30",
        "option_type": option_type,
        "futures_price": current_futures,
        "previous_futures_price": previous_futures,
        "strike": strike,
        "years_to_expiry": years,
        "option_bid": current_mid - 0.5,
        "option_ask": current_mid + 0.5,
        "previous_option_bid": previous_mid - 0.5,
        "previous_option_ask": previous_mid + 0.5,
        "reference_iv": vol,
        "previous_reference_iv": vol,
        "elapsed_seconds": 60.0,
        "futures_return_z": -2.2 if bearish else 2.2,
        "futures_ofi_z": -2.0 if bearish else 2.0,
        "option_trade_imbalance_z": 1.5,
        "option_book_imbalance": 0.25,
        "front_iv_shock_z": 0.5,
        "quote_age_ms": 100,
        "dte": 3,
        "is_expiry_day": False,
        "event_blocked": False,
        "tick_size": 0.05,
    }


def _depth() -> str:
    return json.dumps(
        {
            "depth": {
                "buy": [{"price": 100.0, "quantity": 500}],
                "sell": [{"price": 100.5, "quantity": 400}],
            }
        }
    )


def _ready_frames(sessions: int = 30):
    dates = pd.bdate_range("2026-01-01", periods=sessions)
    futures_rows = []
    option_rows = []
    master_rows = [
        {
            "instrument_token": 1,
            "tradingsymbol": "NIFTY26JULFUT",
            "name": "NIFTY",
            "expiry": "2026-07-28",
            "strike": 0,
            "instrument_type": "FUT",
            "segment": "NFO-FUT",
            "exchange": "NFO",
            "lot_size": 65,
        },
        {
            "instrument_token": 2,
            "tradingsymbol": "NIFTY26JUL25000CE",
            "name": "NIFTY",
            "expiry": "2026-07-28",
            "strike": 25000,
            "instrument_type": "CE",
            "segment": "NFO-OPT",
            "exchange": "NFO",
            "lot_size": 65,
        },
        {
            "instrument_token": 3,
            "tradingsymbol": "NIFTY26JUL25000PE",
            "name": "NIFTY",
            "expiry": "2026-07-28",
            "strike": 25000,
            "instrument_type": "PE",
            "segment": "NFO-OPT",
            "exchange": "NFO",
            "lot_size": 65,
        },
        {
            "instrument_token": 4,
            "tradingsymbol": "NIFTY26AUG25000CE",
            "name": "NIFTY",
            "expiry": "2026-08-04",
            "strike": 25000,
            "instrument_type": "CE",
            "segment": "NFO-OPT",
            "exchange": "NFO",
            "lot_size": 65,
        },
        {
            "instrument_token": 5,
            "tradingsymbol": "NIFTY26AUG25000PE",
            "name": "NIFTY",
            "expiry": "2026-08-04",
            "strike": 25000,
            "instrument_type": "PE",
            "segment": "NFO-OPT",
            "exchange": "NFO",
            "lot_size": 65,
        },
    ]
    for date in dates:
        ts = pd.Timestamp(date).tz_localize("Asia/Kolkata") + pd.Timedelta(hours=10)
        futures_rows.append(
            {
                "local_ts": ts,
                "instrument_token": 1,
                "last_price": 25000.0,
                "best_bid": 24999.5,
                "best_ask": 25000.5,
                "depth_json": _depth(),
                "volume": 1000,
            }
        )
        for token in (2, 3, 4, 5):
            option_rows.append(
                {
                    "local_ts": ts,
                    "instrument_token": token,
                    "last_price": 100.25,
                    "best_bid": 100.0,
                    "best_ask": 100.5,
                    "depth_json": _depth(),
                    "volume": 1000,
                }
            )
    return (
        pd.DataFrame(futures_rows),
        pd.DataFrame(option_rows),
        pd.DataFrame(master_rows),
    )


def test_black76_iv_round_trip_and_greeks_are_finite() -> None:
    price = black76_price("CE", 25000.0, 25000.0, 3 / 365, 0.20, 0.065)
    recovered = implied_volatility_black76(
        "CE", price, 25000.0, 25000.0, 3 / 365, 0.065
    )
    greeks = black76_greeks("CE", 25000.0, 25000.0, 3 / 365, recovered, 0.065)
    assert recovered == pytest.approx(0.20, abs=1e-8)
    assert 0.0 < greeks.delta < 1.0
    assert greeks.gamma > 0
    assert greeks.vega > 0
    assert np.isfinite(greeks.theta_per_year)


def test_bullish_ce_underreaction_creates_buy_intent() -> None:
    result = evaluate_repricing_snapshot(
        _snapshot(),
        specification=SPEC,
        variant=SPEC["variant_grid"][0],
    )
    assert result["signal"] is True
    assert result["direction"] == "BULLISH"
    assert result["option_type"] == "CE"
    assert result["entry_quote_side"] == "ASK"
    assert result["repricing_lag"] > result["required_cost_buffer"]
    assert result["is_order_action"] is False


def test_bearish_pe_underreaction_is_symmetric() -> None:
    result = evaluate_repricing_snapshot(
        _snapshot(option_type="PE", bearish=True),
        specification=SPEC,
        variant=SPEC["variant_grid"][0],
    )
    assert result["signal"] is True
    assert result["direction"] == "BEARISH"
    assert result["option_type"] == "PE"
    assert result["repricing_lag"] > result["required_cost_buffer"]


def test_contract_delta_band_is_enforced() -> None:
    result = evaluate_repricing_snapshot(
        _snapshot(strike_override=24500.0),
        specification=SPEC,
        variant=SPEC["variant_grid"][0],
    )
    assert result["signal"] is False
    assert "DELTA_OUTSIDE_FROZEN_BAND" in result["rejection_reasons"]
    assert abs(result["delta"]) > SPEC["contract_selection"]["absolute_delta_max"]


def test_wrong_option_side_and_stale_quote_fail_closed() -> None:
    snapshot = _snapshot(option_type="PE", bearish=False)
    snapshot["quote_age_ms"] = 5000
    result = evaluate_repricing_snapshot(
        snapshot,
        specification=SPEC,
        variant=SPEC["variant_grid"][0],
    )
    assert result["signal"] is False
    assert "OPTION_TYPE_DOES_NOT_MATCH_IMPULSE" in result["rejection_reasons"]
    assert "STALE_OPTION_QUOTE" in result["rejection_reasons"]


def test_front_iv_repricing_without_lag_is_rejected() -> None:
    snapshot = _snapshot()
    snapshot["option_bid"] += 50.0
    snapshot["option_ask"] += 50.0
    snapshot["front_iv_shock_z"] = 3.0
    result = evaluate_repricing_snapshot(
        snapshot,
        specification=SPEC,
        variant=SPEC["variant_grid"][0],
    )
    assert result["signal"] is False
    assert "REPRICING_LAG_NOT_EXECUTABLE" in result["rejection_reasons"]
    assert "FRONT_IV_ALREADY_REPRICED" in result["rejection_reasons"]


def test_signal_fingerprint_ignores_future_outcome_mutation() -> None:
    first = _snapshot()
    first["realized_net_r"] = 0.9
    second = copy.deepcopy(first)
    second["realized_net_r"] = -99.0
    frame_a = pd.DataFrame([first])
    frame_b = pd.DataFrame([second])
    variant = SPEC["variant_grid"][0]
    assert signal_fingerprint(
        frame_a, specification=SPEC, variant=variant
    ) == signal_fingerprint(frame_b, specification=SPEC, variant=variant)


def test_readiness_missing_inputs_is_explicitly_blocked() -> None:
    result = audit_data_readiness(
        futures_ticks=None,
        option_ticks=None,
        instrument_master=None,
        specification=SPEC,
    )
    assert result["ready"] is False
    assert result["verdict"] == "BLOCKED_NEED_OPTION_MICROSTRUCTURE_DATA"
    assert "MISSING_FUTURES_TICK_DATASET" in result["blockers"]
    assert "MISSING_OPTION_TICK_DATASET" in result["blockers"]
    assert "MISSING_SAME_DAY_INSTRUMENT_MASTER" in result["blockers"]


def test_readiness_accepts_complete_synthetic_microstructure() -> None:
    futures, options, master = _ready_frames()
    result = audit_data_readiness(
        futures_ticks=futures,
        option_ticks=options,
        instrument_master=master,
        specification=SPEC,
    )
    assert result["ready"] is True
    assert result["verdict"] == "DATA_READY_FOR_DEVELOPMENT"
    assert result["overlapping_sessions"] == 30
    assert result["option_expiries"] == 2
    assert result["resolved_option_tokens"] == 4


def test_readiness_rejects_option_capture_without_futures_flow() -> None:
    _, options, master = _ready_frames()
    result = audit_data_readiness(
        futures_ticks=None,
        option_ticks=options,
        instrument_master=master,
        specification=SPEC,
    )
    assert result["ready"] is False
    assert "MISSING_FUTURES_TICK_DATASET" in result["blockers"]


def test_blocked_development_evidence_carries_no_candidate() -> None:
    readiness = audit_data_readiness(
        futures_ticks=None,
        option_ticks=None,
        instrument_master=None,
        specification=SPEC,
    )
    evidence = development_evidence_from_readiness(
        readiness,
        specification=SPEC,
        frozen_spec_sha256="a" * 64,
        code_sha="b" * 40,
    )
    assert evidence["verdict"] == "BLOCKED_NEED_OPTION_MICROSTRUCTURE_DATA"
    assert evidence["candidate_count"] == 0
    assert evidence["candidate_bundle_hash"] is None
    assert evidence["fresh_confirmation_loaded"] is False


def test_non_executable_quotes_are_rejected() -> None:
    snapshot = _snapshot()
    snapshot["option_bid"] = snapshot["option_ask"] + 1.0
    with pytest.raises(RepricingLagError, match="non-executable"):
        evaluate_repricing_snapshot(
            snapshot,
            specification=SPEC,
            variant=SPEC["variant_grid"][0],
        )


def test_campaign_registers_dorl_as_fifth_hypothesis_at_exact_budget() -> None:
    contract_path = (
        Path(__file__).resolve().parents[1]
        / "research/structural_edge_campaign/v1_campaign_contract.json"
    )
    contract = CampaignContract.load(contract_path)
    dorl = next(
        item for item in contract.hypotheses if item.hypothesis_id == "DORL_V3"
    )
    assert len(contract.hypotheses) == 5
    assert sum(item.max_variants for item in contract.hypotheses) == 40
    assert dorl.family == "directional_option_repricing_lag_buy"
    assert dorl.max_variants == 4

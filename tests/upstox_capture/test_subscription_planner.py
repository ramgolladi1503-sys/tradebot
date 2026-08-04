import json
import csv
from datetime import date
from pathlib import Path
import pytest
from core.upstox_capture.subscription_planner import (
    build_subscription_plan,
    resolve_option_surface_weekly_monthly,
    is_monthly_by_calendar
)

@pytest.fixture
def mock_instrument_master_full(tmp_path):
    instruments = [
        # Indices
        {"instrument_key": "NSE_INDEX|Nifty 50", "trading_symbol": "NIFTY 50", "instrument_type": "INDEX", "exchange": "NSE"},
        {"instrument_key": "NSE_INDEX|India VIX", "trading_symbol": "INDIA VIX", "instrument_type": "INDEX", "exchange": "NSE"},
        {"instrument_key": "NSE_INDEX|Nifty Bank", "trading_symbol": "NIFTY BANK", "instrument_type": "INDEX", "exchange": "NSE"},
        {"instrument_key": "NSE_INDEX|Nifty Fin Service", "trading_symbol": "NIFTY FINANCIAL SERVICES", "instrument_type": "INDEX", "exchange": "NSE"},
        {"instrument_key": "NSE_INDEX|Nifty IT", "trading_symbol": "NIFTY IT", "instrument_type": "INDEX", "exchange": "NSE"},
        {"instrument_key": "NSE_INDEX|Nifty Auto", "trading_symbol": "NIFTY AUTO", "instrument_type": "INDEX", "exchange": "NSE"},
        {"instrument_key": "NSE_INDEX|Nifty FMCG", "trading_symbol": "NIFTY FMCG", "instrument_type": "INDEX", "exchange": "NSE"},
        {"instrument_key": "NSE_INDEX|Nifty Pharma", "trading_symbol": "NIFTY PHARMA", "instrument_type": "INDEX", "exchange": "NSE"},
        {"instrument_key": "NSE_INDEX|Nifty Metal", "trading_symbol": "NIFTY METAL", "instrument_type": "INDEX", "exchange": "NSE"},
        {"instrument_key": "NSE_INDEX|Nifty Energy", "trading_symbol": "NIFTY ENERGY", "instrument_type": "INDEX", "exchange": "NSE"},

        # Futures (Front & Next)
        {"instrument_key": "NSE_FO|FUT1", "name": "NIFTY", "instrument_type": "FUT", "expiry": "2026-08-27"},
        {"instrument_key": "NSE_FO|FUT2", "name": "NIFTY", "instrument_type": "FUT", "expiry": "2026-09-24"},
        {"instrument_key": "NSE_FO|FUT_BANK", "name": "BANKNIFTY", "instrument_type": "FUT", "expiry": "2026-08-27"},
    ]

    # Weekly options for 2026-08-06 (ATM=24500, +-10 strikes step 50 -> 23500 to 25500)
    weekly_exp = "2026-08-06"
    for s in range(23500, 25550, 50):
        instruments.append({
            "instrument_key": f"NSE_FO|W_CE_{s}", "name": "NIFTY", "instrument_type": "CE",
            "expiry": weekly_exp, "weekly": True, "strike_price": float(s)
        })
        instruments.append({
            "instrument_key": f"NSE_FO|W_PE_{s}", "name": "NIFTY", "instrument_type": "PE",
            "expiry": weekly_exp, "weekly": True, "strike_price": float(s)
        })

    # Monthly options for 2026-08-27 (ATM=24500, +-5 strikes step 50 -> 24250 to 24750)
    monthly_exp = "2026-08-27"
    for s in range(24250, 24800, 50):
        instruments.append({
            "instrument_key": f"NSE_FO|M_CE_{s}", "name": "NIFTY", "instrument_type": "CE",
            "expiry": monthly_exp, "weekly": False, "strike_price": float(s)
        })
        instruments.append({
            "instrument_key": f"NSE_FO|M_PE_{s}", "name": "NIFTY", "instrument_type": "PE",
            "expiry": monthly_exp, "weekly": False, "strike_price": float(s)
        })

    # 50 Constituents
    constituents = [
        "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
        "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL",
        "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
        "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
        "HINDUNILVR", "ICICIBANK", "ITC", "INFY", "INDIGO",
        "JSWSTEEL", "JIOFIN", "KOTAKBANK", "LT", "M&M",
        "MARUTI", "MAXHEALTH", "NTPC", "NESTLEIND", "ONGC",
        "POWERGRID", "RELIANCE", "SBILIFE", "SHRIRAMFIN", "SBIN",
        "SUNPHARMA", "TCS", "TATACONSUM", "TMPV", "TATASTEEL",
        "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO"
    ]
    for idx, sym in enumerate(constituents):
        instruments.append({
            "instrument_key": f"NSE_EQ|INE{idx:06d}",
            "trading_symbol": sym,
            "instrument_type": "EQ",
            "exchange": "NSE"
        })

    path = tmp_path / "complete.json"
    with open(path, "w") as f:
        json.dump(instruments, f)
    return path

def test_calendar_monthly_rule():
    # 2026-08-27 is last Thursday of August 2026
    assert is_monthly_by_calendar(date(2026, 8, 27)) is True
    # 2026-08-20 is third Thursday of August 2026
    assert is_monthly_by_calendar(date(2026, 8, 20)) is False

def test_resolve_option_surface(mock_instrument_master_full):
    with open(mock_instrument_master_full) as f:
        insts = json.load(f)

    keys, report = resolve_option_surface_weekly_monthly(insts, "NIFTY", 24500.0, reference_date=date(2026, 8, 4))

    assert report["status"] == "PASS"
    assert report["weekly_expiry"] == "2026-08-06"
    assert report["monthly_expiry"] == "2026-08-27"
    assert report["weekly_ce_count"] == 21
    assert report["weekly_pe_count"] == 21
    assert report["monthly_ce_count"] == 11
    assert report["monthly_pe_count"] == 11
    assert report["atm_present"] is True
    assert report["distinct_expiries"] is True

def test_subscription_planner_restricted(mock_instrument_master_full, tmp_path):
    output_dir = tmp_path / "plan_out"
    ref_date = date(2026, 8, 4)

    plan, budget = build_subscription_plan(
        mock_instrument_master_full, output_dir, nifty_spot=24500.0, reference_date=ref_date, restrict_universe=True
    )

    assert budget["budget_verdict"] == "PASS_SUBSCRIPTION_BUDGET"

    full_keys = set(plan["full"])
    # NIFTY Index & Sector indices present
    assert "NSE_INDEX|Nifty 50" in full_keys
    assert "NSE_INDEX|India VIX" in full_keys
    assert "NSE_INDEX|Nifty Bank" in full_keys

    # NIFTY Futures present
    assert "NSE_FO|FUT1" in full_keys
    assert "NSE_FO|FUT2" in full_keys

    # BANKNIFTY Futures absent (restricted)
    assert "NSE_FO|FUT_BANK" not in full_keys

    # Option keys present
    assert any("NSE_FO|W_CE_24500" in k for k in full_keys)
    assert any("NSE_FO|M_CE_24500" in k for k in full_keys)

    # Exclusions CSV written
    exclusions_path = output_dir / "exclusions.csv"
    assert exclusions_path.exists()
    with open(exclusions_path) as f:
        reader = csv.reader(f)
        rows = list(reader)
        reasons = [row[2] for row in rows[1:]]
        assert any("BANKNIFTY futures excluded" in r for r in reasons)

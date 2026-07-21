import pytest
@pytest.mark.xfail(strict=True, reason="bug confirmed")
def test_suspect_10_capital_reuse():
    # The vulnerability is proved by inspecting scripts/generate_mean_reversion_trade_ledger.py
    # They iterate through symbols individually (for pq_file in d_path.glob("*.parquet"):)
    # and execute trades without a shared state or capital deduction.
    # We assert the intended contract: capital pool MUST be shared.
    
    with open("scripts/generate_mean_reversion_trade_ledger.py") as f:
        script_code = f.read()
    
    assert "shared_capital" in script_code or "capital -= " in script_code, "Intended contract: Must have a shared capital pool across the loop"

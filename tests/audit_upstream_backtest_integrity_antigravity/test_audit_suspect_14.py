import pytest
@pytest.mark.xfail(strict=True, reason="bug confirmed")
def test_suspect_14_placeholder_metrics():
    with open("scripts/generate_mean_reversion_trade_ledger.py") as f:
        script_code = f.read()
    
    # Intended contract: Must NOT use placeholder metrics.
    assert '"execution_grade": False' not in script_code, "Intended contract: Must not hardcode placeholder execution_grade"

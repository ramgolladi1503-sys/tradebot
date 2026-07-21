import pytest
@pytest.mark.xfail(strict=True, reason="bug confirmed")
def test_suspect_11_stop_target_ambiguity():
    # Prove that the script silently swallows ambiguity
    with open("scripts/generate_mean_reversion_trade_ledger.py") as f:
        script_code = f.read()
    
    # Intended contract: it should explicitly handle or log ambiguity.
    assert "is_ambiguous" in script_code or "AMBIGUOUS" in script_code, "Intended contract: Must flag ambiguous trades"

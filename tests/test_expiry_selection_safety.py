import pytest
from datetime import date
from unittest.mock import patch
from core.option_token_resolver import resolve_option_token

def test_expired_nifty_chains_must_be_rejected():
    """
    Test that explicitly verifies the options candidate pipeline strictly rejects
    expired chains (e.g., 2026-06-16) when the current date is 2026-06-18.
    """
    # Mock _trading_date to return 2026-06-18
    with patch("core.option_token_resolver._trading_date", return_value=date(2026, 6, 18)):
        # Attempting to resolve an expired chain from 2026-06-16
        resolution = resolve_option_token(
            symbol="NIFTY",
            expiry_date=date(2026, 6, 16),
            strike=24100.0,
            option_type="CE"
        )
        
        # Must be completely rejected
        assert resolution is None, "Expired chain 2026-06-16 was incorrectly allowed through the resolver."

def test_valid_current_weekly_chain_is_allowed():
    """
    Verify that the current valid weekly chain is NOT rejected by the expiration gate.
    """
    # Mock _trading_date to return 2026-06-18
    with patch("core.option_token_resolver._trading_date", return_value=date(2026, 6, 18)):
        # Mocking the load instruments to bypass actual file I/O for the purpose of testing the expiry gate
        with patch("core.option_token_resolver._load_instruments") as mock_load:
            # We don't need a real instrument registry, just enough to show it passed the expiry check
            mock_load.return_value = ([], "cache")
            
            # This should not be rejected by the early expired check
            resolution = resolve_option_token(
                symbol="NIFTY",
                expiry_date=date(2026, 6, 23),
                strike=24100.0,
                option_type="CE"
            )
            # It will return None because the mock registry is empty, but mock_load should be called!
            mock_load.assert_called_once()

import pytest
from research.upstox_expired_options.client import UpstoxClient, UpstoxAPIError

def test_missing_token():
    client = UpstoxClient("")
    with pytest.raises(UpstoxAPIError) as exc:
        client.get("http://example.com")
    assert exc.value.code == "MISSING_TOKEN"\n
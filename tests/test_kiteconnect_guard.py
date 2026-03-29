import pytest

try:
    from kiteconnect import KiteConnect
except Exception:  # pragma: no cover
    KiteConnect = None

from core.kite_client import kite_client  # noqa: F401


def test_direct_kiteconnect_instantiation_blocked():
    if KiteConnect is None:
        pytest.skip("kiteconnect not installed")
    with pytest.raises(RuntimeError, match="KiteConnect instantiation is forbidden"):
        KiteConnect(api_key="dummy")

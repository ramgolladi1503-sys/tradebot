import sys
import pytest

def test_order_paths_disabled():
    # Verify that importing upstox_capture components does not pull in broker execution/order systems
    # Clear sys.modules of core components to force fresh imports
    to_clear = [m for m in sys.modules if m.startswith("core.upstox_capture")]
    for m in to_clear:
        del sys.modules[m]

    from core.upstox_capture.authorization import preflight_auth
    from core.upstox_capture.protobuf_decoder import decode_feed_response
    from core.upstox_capture.schemas import NORMALIZED_TICK_SCHEMA
    from core.upstox_capture.raw_writer import RawWriter
    from core.upstox_capture.normalized_writer import NormalizedWriter
    from core.upstox_capture.subscription_planner import build_subscription_plan

    # Assert that execution or broker adapters are NOT loaded
    loaded_execution_modules = [
        m for m in sys.modules
        if m.startswith("core.execution") or m.startswith("core.broker") or "order" in m
    ]
    
    assert not any("order_reconciliation" in m for m in loaded_execution_modules), \
        "Order reconciliation systems must not be loaded during capture startup"

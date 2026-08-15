"""Repository-wide pytest compatibility for canonical feed-authority fixtures.

This file does not alter production behavior. It repairs a stale test harness
contract introduced when feed currentness moved from ad-hoc runtime snapshots to
the canonical paired feed-truth/feed-runtime authority. The existing
``tests/conftest.py`` isolates each test under a fresh ``DATA_ROOT`` but still
seeds a runtime-only artifact. Tests that are not explicitly exercising
missing/invalid canonical-artifact behavior therefore enter unrelated feed
fail-closed paths before reaching the behavior they are intended to test.

The hook runs after normal test setup and writes production-shaped paired
artifacts only for legacy behavior-test modules whose subject is *not* the
canonical artifact loader itself. Negative canonical-artifact tests remain
untouched and continue to fail closed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


_CANONICAL_BASELINE_MODULES = {
    "test_legacy_quarantine.py",
    "test_blocker_lifecycle.py",
    "test_jit_quote_revalidation.py",
    "test_kite_auth_consistency.py",
    "test_live_quote_truth_contract_phase2.py",
    "test_phase2_fallback_contract_firewall.py",
    "test_phase2_live_fallback_disabled.py",
    "test_pr763_callback_persistence_cutover_certification.py",
    "test_readiness_state_machine.py",
}


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_runtest_setup(item):
    """Seed a verified-healthy canonical feed pair after ordinary fixtures run."""

    yield
    test_file = Path(str(item.fspath)).name
    if test_file not in _CANONICAL_BASELINE_MODULES:
        return

    root_raw = os.environ.get("DATA_ROOT")
    if not root_raw:
        return

    from tests.fixtures.canonical_feed_factory import make_valid_canonical_feed_pair

    # These modules exercise behavior downstream of feed readiness.  The
    # baseline therefore has to satisfy the *current* canonical readiness
    # contract, including the freshness/option-verification primitives used by
    # build_canonical_feed_truth_state().  Tests that need degraded/missing feed
    # evidence overwrite this pair explicitly in their own setup.
    make_valid_canonical_feed_pair(
        Path(root_raw) / "logs",
        feed_ok=True,
        runtime_updates={
            "runtime_state": "VERIFIED_HEALTHY",
            "underlying_tick_fresh": True,
            "depth_fresh": True,
            "option_ticks_verified": True,
            "latest_ltp_age_sec": 0.0,
            "latest_depth_age_sec": 0.0,
            "latest_option_tick_age_sec": 0.0,
            "verified_option_symbols": ["NIFTY"],
            "missing_option_symbols": [],
        },
    )

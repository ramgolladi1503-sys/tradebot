"""Temporary PR818 diagnostic plugin; remove before final repair PR."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_runtest_setup(item):
    # Let normal fixtures finish first. The existing autouse fixture writes a
    # runtime-only canonical artifact that lacks the paired feed truth/lineage.
    yield
    root_raw = os.environ.get("DATA_ROOT")
    if not root_raw:
        return
    from tests.fixtures.canonical_feed_factory import make_valid_canonical_feed_pair

    make_valid_canonical_feed_pair(Path(root_raw) / "logs", feed_ok=True)

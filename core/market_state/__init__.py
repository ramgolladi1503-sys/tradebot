"""Compatibility package for production and research market-state APIs.

The repository already contains ``core/market_state.py`` for the production
read-only state model. This package preserves that public API while adding the
research-only causal frame builder.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .representation import MarketStateConfig, build_market_state_frame, state_contract

_legacy_path = Path(__file__).resolve().parents[1] / "market_state.py"
_spec = importlib.util.spec_from_file_location("core._legacy_market_state", _legacy_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"unable to load legacy market-state module: {_legacy_path}")
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)

for _name in dir(_legacy):
    if not _name.startswith("_"):
        globals().setdefault(_name, getattr(_legacy, _name))

__all__ = sorted(
    {
        "MarketStateConfig",
        "build_market_state_frame",
        "state_contract",
        *[name for name in dir(_legacy) if not name.startswith("_")],
    }
)

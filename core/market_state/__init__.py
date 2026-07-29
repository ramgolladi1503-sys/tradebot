"""Compatibility package for production and research market-state APIs.

The repository already contains ``core/market_state.py`` for the production
read-only state model. This package preserves that public API while adding the
research-only causal frame builder.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd

from .representation import (
    MarketStateConfig,
    build_market_state_frame as _build_market_state_frame,
    state_contract,
)


def build_market_state_frame(frame: pd.DataFrame, config: MarketStateConfig | None = None) -> pd.DataFrame:
    """Build research states while preserving session identity on all pandas versions."""

    cfg = config or MarketStateConfig()
    result = _build_market_state_frame(frame, cfg)
    if cfg.session_col not in result.columns:
        source = frame.copy()
        source[cfg.timestamp_col] = pd.to_datetime(source[cfg.timestamp_col], utc=True, errors="raise")
        if cfg.session_col not in source.columns:
            source[cfg.session_col] = source[cfg.timestamp_col].dt.date.astype(str)
        source = source.sort_values([cfg.session_col, cfg.timestamp_col], kind="mergesort").reset_index(drop=True)
        if len(source) != len(result):
            raise ValueError("market-state row count changed while restoring session identity")
        result.insert(0, cfg.session_col, source[cfg.session_col].to_numpy(copy=True))
    return result


_legacy_path = Path(__file__).resolve().parents[1] / "market_state.py"
_legacy_module_name = "core._legacy_market_state"
_spec = importlib.util.spec_from_file_location(_legacy_module_name, _legacy_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"unable to load legacy market-state module: {_legacy_path}")
_legacy = importlib.util.module_from_spec(_spec)
# dataclasses resolves annotation metadata through sys.modules while the module
# is executing, so register the compatibility module before exec_module().
sys.modules[_legacy_module_name] = _legacy
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

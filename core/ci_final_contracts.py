"""Final CI contract repairs with depth behavior deactivated.

Depth subscription contracts now live in ``core.kite_depth_ws``. This wrapper
keeps the remaining TradeBuilder, Phase2, and freshness compatibility patches
until their dedicated cleanup PRs move those behaviors into owning modules.
"""

from __future__ import annotations

from typing import Any

from core import _ci_final_contracts_base as _base


def _patch_without_depth(name: str, module: Any) -> None:
    if module is None:
        return
    if name.startswith("strategies.trade_builder"):
        _base._patch_trade_builder(module)
    elif name.startswith("core.engine_phase2_adapter"):
        _base._patch_phase2(module)
    elif name.startswith("core.freshness_sla"):
        _base._patch_freshness(module)
    # Depth intentionally not patched here. PR #38 moved it to core.kite_depth_ws.


def install() -> None:
    _base._patch_kite_ws = lambda _module: None
    _base._patch = _patch_without_depth
    _base.install()

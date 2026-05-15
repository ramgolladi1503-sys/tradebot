"""Last-mile CI repair hooks with Phase2 and depth behavior deactivated.

Phase2 adapter contracts now live in ``core.engine_phase2_adapter``.
Depth subscription contracts now live in ``core.kite_depth_ws``.

This wrapper preserves only the remaining freshness compatibility hook until the
freshness/readiness cleanup PR moves that behavior into its owning modules.
"""

from __future__ import annotations

from typing import Any

from core import _ci_last5_contracts_base as _base


def _patch_remaining_last5_contracts(name: str, module: Any) -> None:
    if module is None:
        return
    if name.startswith("core.freshness_sla"):
        _base._patch_freshness(module)


def install() -> None:
    _base._patch_phase2 = lambda _module: None
    _base._patch_depth = lambda _module: None
    _base._patch = _patch_remaining_last5_contracts
    _base.install()

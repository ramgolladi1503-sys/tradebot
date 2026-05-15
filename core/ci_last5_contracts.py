"""Last-mile CI repair hooks with Phase2 behavior deactivated.

Phase2 adapter contracts now live in ``core.engine_phase2_adapter``. This
wrapper preserves the remaining depth and freshness compatibility hooks without
installing the old Phase2 import-time patch.
"""

from __future__ import annotations

from typing import Any

from core import _ci_last5_contracts_base as _base


def _patch_without_phase2(name: str, module: Any) -> None:
    if module is None:
        return
    if name.startswith("core.kite_depth_ws"):
        _base._patch_depth(module)
    elif name.startswith("core.freshness_sla"):
        _base._patch_freshness(module)


def install() -> None:
    _base._patch_phase2 = lambda _module: None
    _base._patch = _patch_without_phase2
    _base.install()

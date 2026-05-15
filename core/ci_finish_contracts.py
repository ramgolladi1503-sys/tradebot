"""Finish-line CI contract repairs with depth behavior deactivated."""

from __future__ import annotations

from typing import Any

from core import _ci_finish_contracts_base as _base


def _no_depth_patch(module: Any) -> None:
    return None


def install() -> None:
    _base._patch_depth = _no_depth_patch
    _base.install()

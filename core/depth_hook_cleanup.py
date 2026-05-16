"""Deactivate legacy depth compatibility hooks after the rewrite engine lands.

PR #39 moved the final public depth subscription contracts into
``core.depth_subscription_engine``. The older compatibility modules still contain
broad import hooks that can re-patch ``core.kite_depth_ws`` later in the process.
This module neutralizes only those depth-specific patch paths while leaving
TradeBuilder, Phase2, freshness, readiness, market-data, and other compatibility
hooks intact for their own cleanup PRs.
"""

from __future__ import annotations

import builtins
import importlib
import sys
from types import ModuleType
from typing import Any, Callable

_DEPTH_MODULE_PREFIX = "core.kite_depth_ws"
_HOOK_MODULE_NAMES = (
    "core.ci_compat_contracts",
    "core.ci_last_contracts",
    "core.ci_final_contracts",
    "core.ci_tail_contracts",
    "core.ci_finish_contracts",
    "core.ci_last5_contracts",
    # Some public hook modules delegate to private base modules. Those bases can
    # remain the actual function owner unless neutralized as well.
    "core._ci_compat_contracts_base",
    "core._ci_last_contracts_base",
    "core._ci_final_contracts_base",
    "core._ci_tail_contracts_base",
    "core._ci_finish_contracts_base",
    "core._ci_last5_contracts_base",
)
_DEPTH_PATCH_NAMES = (
    "_patch_kite_ws",
    "_patch_depth",
    "_patch_depth_ws",
)
_INSTALLED = False
_REAPPLYING = False


def _noop_depth_patch(_module: Any = None, *args: Any, **kwargs: Any) -> None:
    return None


def _wrap_patch_dispatch(module: ModuleType) -> None:
    patch = getattr(module, "_patch", None)
    if not callable(patch) or getattr(patch, "_depth_cleanup_skip", False):
        return

    def patch_without_depth(name: str, target_module: Any) -> Any:
        if str(name or "").startswith(_DEPTH_MODULE_PREFIX):
            return None
        return patch(name, target_module)

    patch_without_depth._depth_cleanup_skip = True  # type: ignore[attr-defined]
    setattr(module, "_patch", patch_without_depth)


def _neutralize_module(module: ModuleType) -> None:
    for name in _DEPTH_PATCH_NAMES:
        if hasattr(module, name):
            setattr(module, name, _noop_depth_patch)
    _wrap_patch_dispatch(module)


def _neutralize_loaded_hooks() -> None:
    for name in _HOOK_MODULE_NAMES:
        module = sys.modules.get(name)
        if isinstance(module, ModuleType):
            _neutralize_module(module)


def _patch_importlib() -> None:
    original_import_module = importlib.import_module
    if getattr(original_import_module, "_depth_cleanup_wrapped", False):
        return

    def import_module_without_depth_repatch(name: str, package: str | None = None) -> ModuleType:
        module = original_import_module(name, package)
        if name in _HOOK_MODULE_NAMES and isinstance(module, ModuleType):
            _neutralize_module(module)
        if str(name or "").startswith(_DEPTH_MODULE_PREFIX):
            _reapply_depth_engine()
        return module

    import_module_without_depth_repatch._depth_cleanup_wrapped = True  # type: ignore[attr-defined]
    importlib.import_module = import_module_without_depth_repatch


def _patch_builtins_import() -> None:
    original_import = builtins.__import__
    if getattr(original_import, "_depth_cleanup_wrapped", False):
        return

    def import_without_depth_repatch(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        module = original_import(name, globals, locals, fromlist, level)
        target_names = [str(name or "")]
        for item in fromlist or ():
            target_names.append(f"{name}.{item}")
        for target_name in target_names:
            loaded = sys.modules.get(target_name)
            if target_name in _HOOK_MODULE_NAMES and isinstance(loaded, ModuleType):
                _neutralize_module(loaded)
            if target_name.startswith(_DEPTH_MODULE_PREFIX):
                _reapply_depth_engine()
        return module

    import_without_depth_repatch._depth_cleanup_wrapped = True  # type: ignore[attr-defined]
    builtins.__import__ = import_without_depth_repatch


def _reapply_depth_engine() -> None:
    global _REAPPLYING
    if _REAPPLYING:
        return
    _REAPPLYING = True
    try:
        ws = sys.modules.get("core.kite_depth_ws") or importlib.import_module("core.kite_depth_ws")
        engine = sys.modules.get("core.depth_subscription_engine") or importlib.import_module("core.depth_subscription_engine")
        patch_module: Callable[[Any], None] | None = getattr(engine, "_patch_module", None)
        if callable(patch_module):
            patch_module(ws)
        else:
            install = getattr(engine, "install", None)
            if callable(install):
                install()
    except Exception:
        pass
    finally:
        _REAPPLYING = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        _neutralize_loaded_hooks()
        _reapply_depth_engine()
        return
    _neutralize_loaded_hooks()
    _patch_importlib()
    _patch_builtins_import()
    _reapply_depth_engine()
    _INSTALLED = True

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
_ENGINE_MODULE = "core.depth_subscription_engine"
_TARGET_DEPTH_FUNCTIONS = (
    "build_subscription_tokens",
    "build_depth_subscription_tokens",
    "_prune_stale_option_subscription_tokens",
    "_maybe_refresh_stale_option_subscription_universe",
)
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


def _is_ci_owner(module_name: str) -> bool:
    return module_name.startswith("core.ci_") or module_name.startswith("core._ci_")


def _depth_owner_modules(ws: Any) -> dict[str, str]:
    owners: dict[str, str] = {}
    for name in _TARGET_DEPTH_FUNCTIONS:
        fn = getattr(ws, name, None)
        owners[name] = str(getattr(fn, "__module__", "") or "")
    return owners


def _needs_depth_reapply(ws: Any) -> bool:
    """Return True only when legacy CI hooks own depth functions.

    This deliberately does not re-apply over test/runtime monkeypatches. A test
    lambda usually has a module such as ``tests.test_*``; clobbering that breaks
    callers that monkeypatch ``core.kite_depth_ws`` and then import symbols from
    it inside the function under test.
    """
    owners = _depth_owner_modules(ws)
    return any(_is_ci_owner(module_name) for module_name in owners.values())


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


def _maybe_reapply_depth_engine() -> None:
    ws = sys.modules.get("core.kite_depth_ws")
    if ws is not None and _needs_depth_reapply(ws):
        _reapply_depth_engine(force=True)


def _patch_importlib() -> None:
    original_import_module = importlib.import_module
    if getattr(original_import_module, "_depth_cleanup_wrapped", False):
        return

    def import_module_without_depth_repatch(name: str, package: str | None = None) -> ModuleType:
        module = original_import_module(name, package)
        if name in _HOOK_MODULE_NAMES and isinstance(module, ModuleType):
            _neutralize_module(module)
        if str(name or "").startswith(_DEPTH_MODULE_PREFIX):
            _maybe_reapply_depth_engine()
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
                _maybe_reapply_depth_engine()
        return module

    import_without_depth_repatch._depth_cleanup_wrapped = True  # type: ignore[attr-defined]
    builtins.__import__ = import_without_depth_repatch


def _reapply_depth_engine(*, force: bool = False) -> None:
    global _REAPPLYING
    if _REAPPLYING:
        return
    _REAPPLYING = True
    try:
        ws = sys.modules.get("core.kite_depth_ws") or importlib.import_module("core.kite_depth_ws")
        if not force and not _needs_depth_reapply(ws):
            return
        engine = sys.modules.get(_ENGINE_MODULE) or importlib.import_module(_ENGINE_MODULE)
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
        _maybe_reapply_depth_engine()
        return
    _neutralize_loaded_hooks()
    _patch_importlib()
    _patch_builtins_import()
    _reapply_depth_engine(force=True)
    _INSTALLED = True

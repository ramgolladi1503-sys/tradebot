from __future__ import annotations

import importlib
import sys
import warnings
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CRITICAL_MODULES = (
    "core.time_utils",
    "core.paths",
    "core.events",
    "core.health_scenarios",
    "core.health_gate",
    "core.go_live_scorecard",
    "core.reconciliation_project_from_events",
    "core.gpt_advisor",
    "core.option_token_resolver",
    "dashboard.models",
    "dashboard.loaders",
    "dashboard.loader_adapters",
)


def _is_our_warning(msg: warnings.WarningMessage) -> bool:
    filename = str(getattr(msg, "filename", "") or "")
    if not filename:
        return False
    normalized = filename.replace("\\", "/")
    root_text = str(ROOT).replace("\\", "/")
    return normalized.startswith(root_text + "/")


def test_critical_modules_no_datetime_utcnow_source_scan() -> None:
    offenders: list[str] = []
    module_to_path = {
        name: ROOT / Path(*name.split(".")).with_suffix(".py")
        for name in CRITICAL_MODULES
    }
    for module_name, path in module_to_path.items():
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "datetime.utcnow(" in text:
            offenders.append(f"{module_name}:{path}")
    assert not offenders, (
        "datetime.utcnow() is forbidden in critical modules; use core.time_utils.utc_now(). "
        + "Offenders: "
        + ", ".join(offenders)
    )


def test_critical_modules_emit_no_own_deprecation_warnings_on_import() -> None:
    for name in CRITICAL_MODULES:
        sys.modules.pop(name, None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        for name in CRITICAL_MODULES:
            importlib.import_module(name)

    own_deprecations = [
        warning
        for warning in caught
        if issubclass(warning.category, DeprecationWarning) and _is_our_warning(warning)
    ]
    assert not own_deprecations, (
        "DeprecationWarning emitted from tradebot critical modules: "
        + "; ".join(
            f"{Path(str(w.filename)).name}:{w.lineno}: {w.message}"
            for w in own_deprecations
        )
    )

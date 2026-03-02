from __future__ import annotations

import importlib
import sys
import warnings
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = ROOT / "core"

_CRITICAL_PREFIXES = (
    "health_gate",
    "events",
    "reconciliation",
    "paths",
    "option_token_resolver",
    "gpt_advisor",
)


def _critical_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(CORE_DIR.glob("*.py")):
        stem = path.stem
        if any(stem.startswith(prefix) for prefix in _CRITICAL_PREFIXES):
            files.append(path)
    return files


def _critical_module_names() -> list[str]:
    return [f"core.{path.stem}" for path in _critical_files()]


def _is_our_core_warning(w: warnings.WarningMessage) -> bool:
    filename = str(getattr(w, "filename", "") or "")
    if "/core/" in filename.replace("\\", "/"):
        return True
    return False


def test_critical_modules_do_not_use_datetime_utcnow() -> None:
    offenders: list[str] = []
    for path in _critical_files():
        text = path.read_text(encoding="utf-8")
        if "datetime.utcnow(" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "datetime.utcnow() is forbidden in critical modules. "
        "Use core.time_utils.utc_now() instead. Offenders: "
        + ", ".join(offenders)
    )


def test_critical_modules_emit_no_deprecation_warnings_on_import() -> None:
    module_names = _critical_module_names()
    for name in module_names:
        sys.modules.pop(name, None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        for name in module_names:
            importlib.import_module(name)

    own_deprecations = [
        w for w in caught if issubclass(w.category, DeprecationWarning) and _is_our_core_warning(w)
    ]
    assert not own_deprecations, (
        "DeprecationWarning emitted from critical core modules: "
        + "; ".join(
            f"{Path(str(w.filename)).name}:{w.lineno}: {w.message}" for w in own_deprecations
        )
    )

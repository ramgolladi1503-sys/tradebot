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
    import subprocess
    import os
    module_names = _critical_module_names()
    offenders = []
    
    for name in module_names:
        try:
            # -W error::DeprecationWarning ensures any DeprecationWarning becomes an exception
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT)
            
            subprocess.check_output(
                [sys.executable, "-W", "error::DeprecationWarning", "-c", f"import {name}"],
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            output = e.output
            if "DeprecationWarning" in output:
                if "/tradebot/" in output and ("core/" in output):
                    offenders.append(f"{name}: {output.strip()}")

    assert not offenders, (
        "Critical core modules MUST NOT emit deprecation warnings during their own import. "
        + "Found warnings:\n"
        + "\n".join(offenders)
    )

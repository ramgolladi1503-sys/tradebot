from __future__ import annotations

import importlib
import sys
import warnings
import os
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
    import subprocess
    offenders = []
    
    for name in CRITICAL_MODULES:
        try:
            # -W error::DeprecationWarning ensures any DeprecationWarning becomes an exception
            # We must set PYTHONPATH so imports work correctly
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT)
            
            # We catch ONLY our own deprecation warnings by filtering the traceback or output
            # Actually, the simplest way is to catch stderr and see if it's from our files.
            out = subprocess.check_output(
                [sys.executable, "-W", "error::DeprecationWarning", "-c", f"import {name}"],
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            output = e.output
            if "DeprecationWarning" in output:
                # Check if it's from one of our files
                if "/tradebot/" in output and ("dashboard/" in output or "core/" in output):
                    offenders.append(f"{name}: {output.strip()}")

    assert not offenders, (
        "Critical modules MUST NOT emit deprecation warnings during their own import. "
        + "Found warnings:\n"
        + "\n".join(offenders)
    )

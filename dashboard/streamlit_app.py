"""Headless-safe entrypoint for the Streamlit dashboard.

Migration note:
Importing this module outside Streamlit runtime now avoids bootstrapping the full UI,
so smoke-import checks do not require local dashboard data files.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import runpy
import traceback


def fmt_conf(conf) -> str:
    try:
        val = float(conf)
    except Exception:
        return "n/a"
    if not math.isfinite(val):
        return "n/a"
    return f"{val:.2f}"


def _should_bootstrap_runtime() -> bool:
    if __name__ == "__main__":
        return True
    if os.getenv("STREAMLIT_SERVER_PORT"):
        return True
    if os.getenv("STREAMLIT_RUNTIME"):
        return True
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


def _bootstrap_runtime() -> None:
    runtime_path = Path(__file__).with_name("streamlit_app_runtime.py")
    try:
        # Execute runtime script on every Streamlit rerun; do not rely on module import cache.
        runpy.run_path(str(runtime_path), run_name="__main__")
    except Exception as exc:
        # Never leave operator with blank page: render a hard error panel with traceback.
        try:
            import streamlit as st

            st.error("Dashboard render failure.")
            st.exception(exc)
            st.code(traceback.format_exc())
        except Exception:
            # Last-resort fallback for non-Streamlit contexts.
            print(f"[DASHBOARD][ERROR] {type(exc).__name__}: {exc}")
            print(traceback.format_exc())


if _should_bootstrap_runtime():
    _bootstrap_runtime()

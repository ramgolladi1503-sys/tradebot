from .tokens import TOKENS
from .components import (
    apply_global_style,
    app_shell as _base_app_shell,
    end_shell,
    section_header,
    card,
    status_badge,
    empty_state,
    error_state,
    warn_state,
    success_state,
    loading_state,
    table,
    confirm_action,
    notify,
    render_notifications,
)
from .freshness_panel import (
    build_freshness_panel_row,
    collect_latest_artifact_freshness_rows,
    render_latest_artifact_freshness_panel,
    summarize_freshness_panel_rows,
)


def _streamlit_module():
    import streamlit as st

    return st


def _render_home_freshness_panel(st_module):
    from dashboard.home_freshness_panel import render_home_freshness_panel

    return render_home_freshness_panel(st_module)


def app_shell(title: str, nav_items: list[str], default_tab: str | None, on_change=None):
    nav = _base_app_shell(title, nav_items, default_tab, on_change=on_change)
    if str(nav or "") == "Home":
        try:
            _render_home_freshness_panel(_streamlit_module())
        except Exception:
            pass
    return nav


__all__ = [
    "TOKENS",
    "apply_global_style",
    "app_shell",
    "end_shell",
    "section_header",
    "card",
    "status_badge",
    "empty_state",
    "error_state",
    "warn_state",
    "success_state",
    "loading_state",
    "table",
    "confirm_action",
    "notify",
    "render_notifications",
    "build_freshness_panel_row",
    "collect_latest_artifact_freshness_rows",
    "render_latest_artifact_freshness_panel",
    "summarize_freshness_panel_rows",
]

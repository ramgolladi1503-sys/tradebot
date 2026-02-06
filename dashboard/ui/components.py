from __future__ import annotations

import hashlib
import math
from datetime import datetime
from typing import Iterable

import streamlit as st

from .tokens import TOKENS, css as _css


def apply_global_style():
    st.markdown(_css(TOKENS), unsafe_allow_html=True)


def app_shell(title: str, nav_items: list[str], default_tab: str | None, on_change=None):
    with st.sidebar:
        st.markdown("### Navigation")
        if "nav_choice" not in st.session_state and default_tab:
            st.session_state["nav_choice"] = default_tab
        nav = st.radio(
            "Sections",
            nav_items,
            index=nav_items.index(st.session_state.get("nav_choice", default_tab or nav_items[0])),
            key="nav_choice",
            on_change=on_change,
        )
    st.markdown(
        f"""
        <div class="app-shell-header">
          <div class="app-shell-title">{title}</div>
          <div class="breadcrumbs">{title} / {nav}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div class='app-container'>", unsafe_allow_html=True)
    return nav


def end_shell():
    st.markdown("</div>", unsafe_allow_html=True)


def section_header(title: str, helper: str | None = None):
    st.markdown(f"<div class='section-title'>{title}</div>", unsafe_allow_html=True)
    if helper:
        st.caption(helper)


def card(content: str):
    st.markdown(f"<div class='card'>{content}</div>", unsafe_allow_html=True)


def status_badge(text: str, status: str = "warn"):
    status = status.lower()
    if status not in ("success", "warn", "error"):
        status = "warn"
    st.markdown(f"<span class='badge {status}'>{text}</span>", unsafe_allow_html=True)


def empty_state(title: str, body: str = ""):
    st.markdown(f"<div class='empty-state'><strong>{title}</strong><div>{body}</div></div>", unsafe_allow_html=True)


def error_state(message: str):
    st.markdown(f"<div class='banner error'>{message}</div>", unsafe_allow_html=True)


def warn_state(message: str):
    st.markdown(f"<div class='banner warn'>{message}</div>", unsafe_allow_html=True)


def success_state(message: str):
    st.markdown(f"<div class='banner success'>{message}</div>", unsafe_allow_html=True)


def loading_state(lines: int = 3):
    st.markdown("".join(["<div class='skeleton'></div>" for _ in range(lines)]), unsafe_allow_html=True)


def _stable_key(df, salt: str | None = None):
    h = hashlib.md5()
    h.update(str(df.columns.tolist()).encode("utf-8"))
    h.update(str(len(df)).encode("utf-8"))
    if salt:
        h.update(salt.encode("utf-8"))
    return f"tbl_{h.hexdigest()}"


def table(df, key: str | None = None, page_size: int = 20, height: int = 420, empty_title: str = "No data", empty_body: str = "", **_kwargs):
    if df is None or df.empty:
        empty_state(empty_title, empty_body)
        return
    key = key or _stable_key(df)
    total = len(df)
    pages = max(1, math.ceil(total / page_size))
    page = 1
    if pages > 1:
        page = st.number_input("Page", min_value=1, max_value=pages, value=1, step=1, key=f"{key}_page")
        st.caption(f"Page {page}/{pages} • {total} rows")
    start = (page - 1) * page_size
    view = df.iloc[start:start + page_size]
    html = view.to_html(index=False, classes="rt-table", escape=True)
    st.markdown(f"<div class='rt-table-wrap' style='max-height:{height}px'>{html}</div>", unsafe_allow_html=True)


def confirm_action(key: str, label: str, help_text: str = "Are you sure?", confirm_label: str = "Confirm", cancel_label: str = "Cancel"):
    if st.button(label, key=f"{key}_btn"):
        st.session_state[f"{key}_confirm"] = True
    if st.session_state.get(f"{key}_confirm"):
        warn_state(help_text)
        c1, c2 = st.columns([1, 1])
        if c1.button(confirm_label, key=f"{key}_confirm_btn"):
            st.session_state[f"{key}_confirm"] = False
            return True
        if c2.button(cancel_label, key=f"{key}_cancel_btn"):
            st.session_state[f"{key}_confirm"] = False
    return False


def notify(kind: str, message: str):
    items = st.session_state.get("notifications", [])
    items.append({"ts": datetime.now().isoformat(), "kind": kind, "message": message})
    st.session_state["notifications"] = items[-5:]


def render_notifications():
    items = st.session_state.get("notifications", [])
    if not items:
        return
    with st.container():
        cols = st.columns([8, 1])
        with cols[0]:
            for n in items:
                kind = n.get("kind", "warn")
                msg = n.get("message", "")
                if kind == "success":
                    success_state(msg)
                elif kind == "error":
                    error_state(msg)
                else:
                    warn_state(msg)
        with cols[1]:
            if st.button("Clear", key="clear_notifications"):
                st.session_state["notifications"] = []

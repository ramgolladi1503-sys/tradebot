from __future__ import annotations

import pandas as pd

import dashboard.streamlit_app_runtime as runtime


def test_advisory_table_uses_top_advisory_snapshot():
    top_adv = pd.DataFrame({"trade_id": ["adv_1", "adv_2"]})
    top_frames = {"top_advisory": top_adv, "top_executable": pd.DataFrame()}
    suggested_live_df = pd.DataFrame({"trade_id": ["raw_1"]})

    df, source = runtime._select_advisory_table_source(
        show_exec_only=False,
        top_frames=top_frames,
        suggested_live_df=suggested_live_df,
    )

    assert source == "top_advisory_snapshot"
    assert list(df["trade_id"]) == ["adv_1", "adv_2"]


def test_exec_only_uses_top_executable_snapshot():
    top_exec = pd.DataFrame({"trade_id": ["exec_1"]})
    top_frames = {"top_advisory": pd.DataFrame(), "top_executable": top_exec}
    suggested_live_df = pd.DataFrame({"trade_id": ["raw_1"]})

    df, source = runtime._select_advisory_table_source(
        show_exec_only=True,
        top_frames=top_frames,
        suggested_live_df=suggested_live_df,
    )

    assert source == "top_executable_snapshot"
    assert list(df["trade_id"]) == ["exec_1"]


def test_advisory_fallback_uses_visible_rows(monkeypatch):
    fallback_df = pd.DataFrame({"trade_id": ["fallback_1"]})
    top_frames = {"top_advisory": pd.DataFrame(), "top_executable": pd.DataFrame()}
    suggested_live_df = pd.DataFrame({"trade_id": ["raw_1"]})

    monkeypatch.setattr(runtime, "_select_visible_advisory_rows", lambda _df: fallback_df, raising=True)

    df, source = runtime._select_advisory_table_source(
        show_exec_only=False,
        top_frames=top_frames,
        suggested_live_df=suggested_live_df,
    )

    assert source == "advisory_fallback_visible"
    assert list(df["trade_id"]) == ["fallback_1"]


def test_exec_only_fallback_uses_executable_rows(monkeypatch):
    fallback_df = pd.DataFrame({"trade_id": ["fallback_exec"]})
    top_frames = {"top_advisory": pd.DataFrame(), "top_executable": pd.DataFrame()}
    suggested_live_df = pd.DataFrame({"trade_id": ["raw_1"]})

    monkeypatch.setattr(runtime, "_select_executable_suggestion_rows", lambda _df: fallback_df, raising=True)

    df, source = runtime._select_advisory_table_source(
        show_exec_only=True,
        top_frames=top_frames,
        suggested_live_df=suggested_live_df,
    )

    assert source == "advisory_fallback_executable"
    assert list(df["trade_id"]) == ["fallback_exec"]


def test_ranked_snapshot_order_is_preserved():
    top_adv = pd.DataFrame({"trade_id": ["adv_b", "adv_a"]})
    top_frames = {"top_advisory": top_adv, "top_executable": pd.DataFrame()}
    suggested_live_df = pd.DataFrame({"trade_id": ["raw_1"]})

    df, source = runtime._select_advisory_table_source(
        show_exec_only=False,
        top_frames=top_frames,
        suggested_live_df=suggested_live_df,
    )

    assert source == "top_advisory_snapshot"
    assert list(df["trade_id"]) == ["adv_b", "adv_a"]

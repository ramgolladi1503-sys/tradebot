from __future__ import annotations

import pandas as pd
import pytest

import dashboard.streamlit_app_runtime as runtime


pytestmark = [pytest.mark.behavior, pytest.mark.regression, pytest.mark.ui_read_model]


def test_executable_pool_is_primary_until_operator_opens_advisory_debug_view():
    assert runtime._show_executable_primary(False) is True
    assert runtime._show_executable_primary(True) is False


def test_primary_pool_selection_never_mixes_advisory_and_executable_rows():
    executable = pd.DataFrame(
        [
            {
                "trade_id": "EXEC-1",
                "candidate_class": "EXECUTABLE",
                "execution_allowed": True,
                "rank_global": 1,
            }
        ]
    )
    advisory = pd.DataFrame(
        [
            {
                "trade_id": "FALLBACK-1",
                "candidate_class": "ADVISORY_ONLY",
                "execution_allowed": False,
                "row_kind": "recovered_fallback",
                "rank_global": 1,
            }
        ]
    )
    frames = {"top_executable": executable, "top_advisory": advisory}

    primary, primary_source = runtime._select_advisory_table_source(
        show_exec_only=runtime._show_executable_primary(False),
        top_frames=frames,
        suggested_live_df=pd.DataFrame(),
    )
    debug, debug_source = runtime._select_advisory_table_source(
        show_exec_only=runtime._show_executable_primary(True),
        top_frames=frames,
        suggested_live_df=pd.DataFrame(),
    )

    assert primary_source == "top_executable_snapshot"
    assert list(primary["trade_id"]) == ["EXEC-1"]
    assert debug_source == "top_advisory_snapshot"
    assert list(debug["trade_id"]) == ["FALLBACK-1"]
    assert set(primary["trade_id"]).isdisjoint(set(debug["trade_id"]))

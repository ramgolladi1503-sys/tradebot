from __future__ import annotations

import pandas as pd
import streamlit as st


def render_score_distribution(metrics: dict) -> None:
    st.caption("Score Distribution")
    score_df = pd.DataFrame(metrics.get("score_distribution") or [])
    if score_df.empty:
        st.caption("No persisted score fields available yet.")
    else:
        chart_df = score_df.copy()
        chart_df["bucket"] = chart_df["bucket"].astype(str)
        st.bar_chart(chart_df.set_index("bucket")["count"])
        st.dataframe(chart_df, use_container_width=True)

    field_df = pd.DataFrame(metrics.get("score_field_usage") or [])
    if not field_df.empty:
        st.caption("Score field usage")
        st.dataframe(field_df, use_container_width=True)

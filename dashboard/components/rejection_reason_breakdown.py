from __future__ import annotations

import pandas as pd
import streamlit as st


def render_rejection_reason_breakdown(metrics: dict) -> None:
    left, right = st.columns(2)

    with left:
        st.caption("Rejection reason distribution")
        rejection_df = pd.DataFrame(metrics.get("rejection_reason_distribution") or [])
        if rejection_df.empty:
            st.caption("No rejection reasons available from persisted runtime artifacts.")
        else:
            st.bar_chart(rejection_df.set_index("reason")["count"])
            st.dataframe(rejection_df, use_container_width=True)

    with right:
        st.caption("Blockers distribution")
        blockers_df = pd.DataFrame(metrics.get("blockers_distribution") or [])
        if blockers_df.empty:
            st.caption("No blockers captured in current runtime artifacts.")
        else:
            st.bar_chart(blockers_df.set_index("blocker")["count"])
            st.dataframe(blockers_df, use_container_width=True)

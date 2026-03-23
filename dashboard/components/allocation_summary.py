from __future__ import annotations

import pandas as pd
import streamlit as st


def render_allocation_summary(metrics: dict) -> None:
    summary = dict(metrics.get("allocation_summary") or {})
    cols = st.columns(4)
    cols[0].metric("Allocated", int(summary.get("accepted_count") or 0))
    cols[1].metric("Rejected/Deferred", int(summary.get("rejected_count") or 0))
    cols[2].metric("Acceptance rate", f"{100.0 * float(summary.get('acceptance_rate') or 0.0):.1f}%")
    cols[3].metric("Capital assigned", f"{float(summary.get('capital_assigned_total') or 0.0):.2f}")

    reason_df = pd.DataFrame(summary.get("reason_distribution") or [])
    st.caption("Allocation acceptance/rejection summary")
    if reason_df.empty:
        st.caption("No allocation decisions captured in current runtime artifacts.")
        return
    st.bar_chart(reason_df.set_index("reason")["count"])
    st.dataframe(reason_df, use_container_width=True)

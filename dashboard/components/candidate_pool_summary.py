from __future__ import annotations

import pandas as pd
import streamlit as st


def render_candidate_pool_summary(metrics: dict) -> None:
    summary = dict(metrics.get("summary") or {})
    top_strategy = summary.get("top_strategy_by_candidate_volume") or {}
    cycle_rows = pd.DataFrame(metrics.get("candidate_pool_by_cycle") or [])

    cols = st.columns(4)
    cols[0].metric("Candidate pool", int(summary.get("candidate_pool_latest") or 0))
    cols[1].metric("Ranked candidates", int(summary.get("ranked_candidate_count") or 0))
    cols[2].metric(
        "Top strategy",
        str(top_strategy.get("strategy") or "n/a"),
        delta=(f"{int(top_strategy.get('count') or 0)} candidates" if top_strategy else None),
    )
    cols[3].metric(
        "Adv->Exec conversion",
        f"{100.0 * float(summary.get('advisory_to_execution_conversion_rate') or 0.0):.1f}%",
        delta=(
            f"{int(summary.get('advisory_conversion_numerator') or 0)}/"
            f"{int(summary.get('advisory_conversion_denominator') or 0)}"
        ),
    )

    latest_funnel = summary.get("latest_pipeline_funnel") or {}
    if latest_funnel:
        st.caption(
            "Latest funnel: "
            f"candidates={int(latest_funnel.get('candidates') or 0)}, "
            f"scored={int(latest_funnel.get('scored') or 0)}, "
            f"ready={int(latest_funnel.get('ready') or 0)}, "
            f"executable={int(latest_funnel.get('executable') or 0)}, "
            f"emitted={int(latest_funnel.get('emitted') or 0)}"
        )

    if cycle_rows.empty:
        st.caption("No candidate-pool history available from persisted runtime artifacts.")
        return

    chart_df = cycle_rows[["cycle", "candidate_pool_size"]].copy()
    chart_df["cycle"] = chart_df["cycle"].astype(str)
    st.bar_chart(chart_df.set_index("cycle")["candidate_pool_size"])
    st.dataframe(chart_df, use_container_width=True)

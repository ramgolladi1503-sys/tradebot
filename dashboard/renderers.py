from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from dashboard.models import ArtifactVM, DepthVM, GeminiVM, RiskVM


def _render_payload_table(payload: dict) -> None:
    if not payload:
        return
    st.dataframe(pd.DataFrame([payload]), use_container_width=True, hide_index=True)


def _render_artifact(vm: ArtifactVM, *, missing_caption: str, error_caption: str) -> None:
    if vm.status == "missing":
        st.caption(vm.message or missing_caption)
        return
    if vm.status == "error":
        st.warning(vm.message or error_caption)
        return
    if vm.status == "empty":
        st.caption(vm.message or missing_caption)
        return
    _render_payload_table(vm.payload)


def render_execution(vm: ArtifactVM) -> None:
    _render_artifact(
        vm,
        missing_caption="Execution analytics unavailable.",
        error_caption="Execution analytics parse error.",
    )


def render_recon(vm: ArtifactVM) -> None:
    _render_artifact(
        vm,
        missing_caption="Reconciliation summary unavailable.",
        error_caption="Reconciliation parse error.",
    )


def render_feed(vm: ArtifactVM) -> None:
    _render_artifact(
        vm,
        missing_caption="Feed artifact unavailable.",
        error_caption="Feed artifact parse error.",
    )


def render_depth(vm: DepthVM) -> None:
    if vm.status == "error":
        st.warning(vm.message or "Depth status unavailable.")
        return
    if vm.status in {"missing", "empty"}:
        db_msg = f" (db: {vm.db_path})" if vm.db_path else ""
        st.caption((vm.message or "no depth snapshots captured") + db_msg)
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "status": vm.status,
                    "db_path": str(vm.db_path) if vm.db_path else None,
                    "columns": vm.columns,
                    "rows": vm.row_count,
                }
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    if vm.payload:
        st.caption("Latest depth snapshot")
        _render_payload_table(vm.payload)


def render_risk(vm: RiskVM) -> None:
    _render_artifact(
        vm,
        missing_caption="Risk artifact unavailable.",
        error_caption="Risk artifact parse error.",
    )


def render_gemini(vm: GeminiVM) -> None:
    provider = str(vm.provider or os.getenv("GPT_PROVIDER", "openai")).strip().lower()
    provider_label = "Gemini" if provider == "gemini" else "OpenAI"
    model_name = vm.model or str(vm.payload.get("model") or "unknown")
    st.caption(f"AI Advice ({provider_label}) | model: {model_name}")
    _render_artifact(
        vm,
        missing_caption="Gemini/OpenAI usage artifact unavailable.",
        error_caption="Gemini/OpenAI usage artifact parse error.",
    )


# Backward-compatible runtime callsites.
def render_execution_panel(vm: ArtifactVM) -> None:
    render_execution(vm)


def render_recon_panel(vm: ArtifactVM) -> None:
    render_recon(vm)


def render_feed_panel(vm: ArtifactVM) -> None:
    render_feed(vm)


def render_depth_panel(vm: DepthVM) -> None:
    render_depth(vm)


def render_risk_panel(vm: RiskVM) -> None:
    render_risk(vm)


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
    if vm.status == "missing":
        st.caption(vm.message or "Feed artifact unavailable.")
        return
    if vm.status == "error":
        st.warning(vm.message or "Feed artifact parse error.")
    payload = dict(vm.payload or {})
    source = str(payload.get("freshness_source") or "")
    if source == "snapshot_v1":
        freshness = payload.get("freshness") if isinstance(payload.get("freshness"), dict) else {}
        runtime_health = payload.get("runtime_health") if isinstance(payload.get("runtime_health"), dict) else {}
        st.caption("Freshness source: MarketSnapshotV1.freshness + health_gate.evaluate_runtime_health")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "status_light": payload.get("status_light"),
                        "snapshot_id": payload.get("snapshot_id"),
                        "max_tick_age_sec": freshness.get("max_tick_age_sec"),
                        "sla_threshold_sec": freshness.get("sla_threshold_sec"),
                        "stale_tokens_count": freshness.get("stale_tokens_count"),
                        "runtime_ok": runtime_health.get("ok"),
                    }
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        blockers = runtime_health.get("blockers") if isinstance(runtime_health.get("blockers"), list) else []
        if blockers:
            st.caption("Runtime blockers")
            st.dataframe(pd.DataFrame(blockers), use_container_width=True, hide_index=True)
        return

    if source == "legacy_runtime_health":
        st.caption("Freshness source: legacy_runtime_health (display only; not used for status lights)")
    _render_payload_table(payload)


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

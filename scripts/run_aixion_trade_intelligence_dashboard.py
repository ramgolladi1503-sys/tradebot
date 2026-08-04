from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _load(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dashboard_input_not_object")
    return payload


def _session_payload(payload: Mapping[str, object]) -> tuple[Mapping[str, object], Mapping[str, object]]:
    nested = payload.get("session_analysis")
    if isinstance(nested, Mapping):
        monitor = {
            "monitoring_verdict": payload.get("monitoring_verdict"),
            "monitoring_valid": payload.get("monitoring_valid"),
            "monitoring_only": payload.get("monitoring_only"),
            "final_session_complete": payload.get("final_session_complete"),
            "blockers": payload.get("blockers"),
        }
        return nested, monitor
    return payload, {}


def _authority_rows(cockpit: Mapping[str, object]) -> list[dict[str, object]]:
    authorities = cockpit.get("authorities")
    if not isinstance(authorities, Mapping):
        raise ValueError("elite_dashboard_authorities_missing")
    rows: list[dict[str, object]] = []
    for name in ("observation", "diagnosis", "strategy_change", "profitability_claim"):
        gate = authorities.get(name)
        if not isinstance(gate, Mapping):
            raise ValueError(f"elite_dashboard_authority_missing={name}")
        reasons = gate.get("reasons")
        if not isinstance(reasons, list):
            raise ValueError(f"elite_dashboard_authority_reasons_invalid={name}")
        rows.append(
            {
                "authority": name,
                "verdict": str(gate.get("verdict") or "UNKNOWN"),
                "passed": bool(gate.get("passed")),
                "reasons": "; ".join(str(value) for value in reasons),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the read-only Aixion dashboard.")
    parser.add_argument("--session-report", required=True)
    parser.add_argument("--campaign-report")
    parser.add_argument("--elite-cockpit")
    args = parser.parse_args()
    try:
        import streamlit as st
    except ImportError as exc:
        raise RuntimeError("streamlit_not_installed") from exc
    session_input = _load(args.session_report)
    session, monitor = _session_payload(session_input)
    campaign = _load(args.campaign_report) if args.campaign_report else None
    elite = _load(args.elite_cockpit) if args.elite_cockpit else None
    st.set_page_config(page_title="Aixion Trade Intelligence", layout="wide")
    st.title("Aixion Trade Intelligence")
    st.caption("Read-only evidence dashboard. No broker or execution authority.")
    manifest = session.get("manifest") if isinstance(session.get("manifest"), dict) else {}
    funnel = session.get("candidate_funnel") if isinstance(session.get("candidate_funnel"), dict) else {}
    readiness = session.get("outcome_readiness") if isinstance(session.get("outcome_readiness"), dict) else {}
    first, second, third, fourth = st.columns(4)
    first.metric("Session", manifest.get("session_id") or "unknown")
    second.metric("Verdict", monitor.get("monitoring_verdict") or manifest.get("verdict") or "unknown")
    third.metric("Events", manifest.get("event_count") or 0)
    fourth.metric("Candidates", funnel.get("candidate_count") or 0)

    if monitor:
        st.subheader("Live monitoring state")
        if bool(monitor.get("monitoring_valid")):
            st.success(str(monitor.get("monitoring_verdict") or "LIVE_MONITORING_HEALTHY"))
        else:
            st.error(str(monitor.get("monitoring_verdict") or "LIVE_MONITORING_BLOCKED"))
        st.json(dict(monitor))

    if elite is not None:
        st.subheader("Elite authority matrix")
        authority_rows = _authority_rows(elite)
        columns = st.columns(4)
        for column, row in zip(columns, authority_rows):
            column.metric(str(row["authority"]), str(row["verdict"]))
            if bool(row["passed"]):
                column.success(str(row["reasons"]))
            else:
                column.error(str(row["reasons"]))
        blockers = elite.get("global_blockers")
        if isinstance(blockers, list) and blockers:
            st.error("Active blockers: " + "; ".join(str(value) for value in blockers))
        ranking = elite.get("ranking") if isinstance(elite.get("ranking"), dict) else {}
        score = ranking.get("score_separation") if isinstance(ranking.get("score_separation"), dict) else {}
        stability = ranking.get("ranking_stability") if isinstance(ranking.get("ranking_stability"), dict) else {}
        empirical = ranking.get("empirical_policy") if isinstance(ranking.get("empirical_policy"), dict) else {}
        st.subheader("Ranking intelligence")
        rank_a, rank_b, rank_c, rank_d = st.columns(4)
        rank_a.metric("Score range", score.get("score_range") if score else "not evaluated")
        rank_b.metric("Top-1 / Top-2 gap", score.get("top1_minus_top2") if score else "not evaluated")
        rank_c.metric("Fallback contamination", score.get("fallback_contamination_rate") if score else "not evaluated")
        rank_d.metric("Executable rate", score.get("executable_rate") if score else "not evaluated")
        if score:
            st.json(score)
        if stability:
            st.subheader("Ranking stability")
            st.json(stability)
        if empirical:
            st.subheader("Empirical ranking baseline")
            st.json(empirical)
        evidence = elite.get("evidence") if isinstance(elite.get("evidence"), dict) else {}
        if evidence:
            st.subheader("Evidence continuity guardian")
            st.json(evidence)

    st.subheader("Data truth")
    st.json(manifest)
    st.subheader("Candidate funnel")
    st.json(funnel)
    st.subheader("Outcome readiness")
    st.json(readiness)
    st.subheader("Runtime timeline")
    st.dataframe(session.get("runtime_timeline") or [], use_container_width=True)
    if campaign is not None:
        st.subheader("Multi-session campaign")
        st.json(campaign)
    st.warning("Dashboard evidence is diagnostic. It does not certify profitability, promote strategies, or place orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Aixion Trade Intelligence Authority Map

This document resolves overlapping modules by assigning one explicit authority to each use case.

| Domain | Authoritative module | Supporting module | Boundary |
|---|---|---|---|
| Canonical event truth | `contracts.py` | `tradebot_adapter.py`, `market_adapters.py` | Adapters translate; contracts decide validity. |
| Runtime capture | `runtime_tailer.py` | `live_sidecar.py`, `core/aixion_intelligence_bridge.py` | Use exactly one transport per session. |
| Session certification | `session.py` | `evidence_guardian.py` | Session analyzer certifies the canonical log; guardian diagnoses source continuity before/alongside it. |
| Causal outcomes | `outcomes.py` | `counterfactuals.py` | Outcomes price observed paths; counterfactuals compare contracts and blocked decisions. |
| Market structure | `market_analytics.py` | `market_event_graph.py`, `event_graph.py` | Analytics calculate metrics; graph modules validate event paths and DAG lead times. |
| CAS | `cas_accumulator.py` for one session | `cas.py` for campaign aggregation | No directional claim from one-session output. |
| Research validation | `validation.py` | `research_validation.py` | `validation.py` owns campaign splits/PBO/DSR; supporting module provides return-series diagnostics. |
| Risk simulation | `risk_analytics.py` | `risk_simulation.py` | Campaign risk report is authoritative; supporting module provides equity-bound summaries. |
| Agent review | `agent_workflow.py` | `analyst_workflow.py` | Workflow owns analyst/critic orchestration; supporting module validates cited claims. |
| RAG | `rag_ingestion.py` + structured analytics | `evidence_search.py` | Numeric questions use deterministic analytics; retrieval supplies documents and citations. |
| Dashboard | `dashboard_read_model.py` | dashboard scripts | Read models only; no new trading calculations in UI code. |
| Certification | `certification.py` | `elite_cockpit.py` | Certification gates own promotion readiness; cockpit presents separated authorities. |

## Non-negotiable rules

1. No supporting module may override its authoritative module.
2. Runtime, direct bridge, and external sidecar must never observe the same source in the same session.
3. Missing or conflicting evidence remains `NOT_EVALUATED` or invalid; it is never replaced by a generic value.
4. LLM or dashboard output cannot change session, risk, profitability, or promotion verdicts.
5. Real-session empirical gates remain blocked until their referenced artifacts exist.

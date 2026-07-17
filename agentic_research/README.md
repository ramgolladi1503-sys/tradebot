# TradeBot Agentic Strategy Research MVP

A read-only LangGraph sidecar that researches `trend_pullback_v1` without modifying TradeBot production architecture, strategy formulas, execution gates, broker integrations, or live-risk controls.

## Phase 0 completed

- Machine-readable strategy contract
- Dataset eligibility contract
- Frozen baseline parameters
- Deterministic certification gates
- Bounded experiment budget

## Phase 1 completed

- Stateful LangGraph Research Manager
- Human approval interrupt and resume
- Six read-only research tools
- Local MCP server
- SQLite checkpoint support
- Deterministic non-LLM certification judge
- FastAPI and Streamlit surfaces
- Immutable evidence bundle per research run
- Gemini action planner with deterministic offline fallback

## Safety boundary

The sidecar has no order, broker, strategy-mutation, risk-limit, or production-promotion tools. The maximum Phase 1 verdict is `READY_FOR_OPTION_REPLAY`; it cannot declare a live options edge.

## Install

```bash
python -m pip install -r agentic_research/requirements.txt
```

## Run

```bash
python -m agentic_research.cli \
  --repo-root . \
  --research-id tp-mvp-001 \
  --dataset agentic_research/sample_data/trend_pullback_fixture.jsonl \
  --approve
```

Use the Gemini planner after setting `GEMINI_API_KEY`:

```bash
python -m agentic_research.cli --repo-root . --research-id tp-gemini-001 --dataset agentic_research/sample_data/trend_pullback_fixture.jsonl --planner gemini --approve
```

Start the dashboard:

```bash
streamlit run agentic_research/dashboard.py
```

Start FastAPI:

```bash
uvicorn agentic_research.server:app
```

The included dataset is only a deterministic workflow fixture. It is not historical-market evidence and cannot support a profitability claim.

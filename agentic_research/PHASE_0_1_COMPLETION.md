# Phase 0 and Phase 1 completion record

## Scope

Build a portfolio-grade, read-only agentic strategy-research sidecar for `trend_pullback_v1` without changing TradeBot production architecture.

## Architecture impact

`NONE` to existing TradeBot runtime architecture. All additions are under `agentic_research/`. No existing production, strategy, feed, broker, order, risk, ranking, orchestrator, or option-replay files were edited.

## Phase 0

Completed:

- frozen machine-readable strategy contract;
- explicit dataset eligibility contract;
- unchanged-production baseline parameters;
- deterministic certification gates;
- bounded experiment budget;
- explicit prohibition of broker access, live orders, production mutation and autonomous promotion.

## Phase 1

Completed:

- LangGraph state machine with bounded manager loop;
- deterministic offline planner and optional Gemini planner;
- six read-only research tools;
- actual `trend_pullback_v1` callable structural replay adapter;
- direct temporal-semantics test adapter;
- structural train/validation/holdout MVP;
- human approval interrupt/resume;
- SQLite checkpoint persistence;
- deterministic non-LLM certification judge;
- local MCP server, FastAPI API, CLI and Streamlit evidence viewer;
- immutable per-run JSON evidence and hashes;
- isolated unit/workflow tests.

## Deliberate ceiling

Phase 1 can issue at most `READY_FOR_OPTION_REPLAY`. The structural MVP does not certify option execution or live profitability. The included fixture is a workflow fixture, not historical-market proof.

## Validation

Run:

```bash
PYTHONPATH=. pytest -q agentic_research/tests
python -m compileall -q agentic_research
```

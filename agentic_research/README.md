# TradeBot Agentic Strategy Research

A portfolio-grade, read-only agentic research and certification sidecar for `trend_pullback_v1`.

The LLM coordinates and critiques. Deterministic TradeBot code owns data validation, strategy execution, metrics, evidence hashes and the final certification verdict.

## Why this is agentic

- LangGraph manager chooses the next bounded action from workflow state.
- Human approval interrupts pause and resume durable investigations.
- Nine read-only MCP tools expose real TradeBot research capabilities.
- An independent critic challenges data, causality, concentration, overfitting and execution assumptions.
- A deterministic judge can reject both the manager and critic conclusions.
- SQLite checkpoints and an idempotent execution ledger prevent duplicate expensive work after restart.
- A hypothesis registry remembers failed proposals and refuses duplicate retests.
- A 64-case evaluation harness tests tool selection, approval enforcement and hostile instructions.

## Hard safety boundary

The sidecar has no order, broker, risk-limit, production-promotion or autonomous strategy-mutation tools. Every repository and dataset string is treated as untrusted evidence. The maximum structural verdict is `READY_FOR_OPTION_REPLAY`, never live profitability.

## One-command interview demo

```bash
python -m pip install -r agentic_research/requirements.txt
python -m agentic_research.portfolio_demo --repo-root .
```

The demo audits the real committed June 29 research report, pauses for approval, rejects the report because it used zero-volume data and same-bar proxy entry, runs an independent critic, creates a deterministic certificate, proposes no fake tuning workaround, and produces the 64-case evaluation report.

## Structural research workflow

```bash
python -m agentic_research.cli \
  --repo-root . \
  --research-id tp-structural-001 \
  --evidence /absolute/path/to/eligible_dataset.jsonl \
  --mode structural \
  --approve
```

## Legacy evidence audit

```bash
python -m agentic_research.cli \
  --repo-root . \
  --research-id tp-legacy-20260629 \
  --evidence runtime/backtests/all_strategy_20260629/all_strategy_report_20260629.json \
  --mode legacy-report \
  --approve
```

## Gemini manager and critic

Set `GEMINI_API_KEY`, then run:

```bash
python -m agentic_research.cli \
  --repo-root . \
  --research-id tp-gemini-001 \
  --evidence /absolute/path/to/evidence.jsonl \
  --planner gemini \
  --critic gemini \
  --approve
```

Run the model evaluation separately and publish the generated report rather than claiming unmeasured accuracy:

```bash
python -m agentic_research.evals \
  --planner gemini \
  --output agentic_research/eval_results/gemini_latest.json
```

## Local services

```bash
python -m agentic_research.mcp_server --repo-root . --transport stdio
uvicorn agentic_research.server:app
streamlit run agentic_research/dashboard.py
```

## Validation

```bash
PYTHONPATH=. pytest -q agentic_research/tests
python -m compileall -q agentic_research
python -m agentic_research.evals --planner deterministic
```

See `agentic_research/KILLER_READINESS.md` and `agentic_research/docs/` for the architecture, threat model, evaluation methodology and interview walkthrough.

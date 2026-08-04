# Aixion Trade Intelligence

## Purpose

A read-only evidence, analytics, RAG and certification layer around TradeBot.
It observes what TradeBot and the market produced, calculates deterministic
metrics, and blocks unsupported promotion claims. It has no order authority.

```text
TradeBot truth and market evidence
→ canonical event stream
→ deterministic replay
→ session and candidate lineage
→ causal outcomes and counterfactuals
→ execution/cost/capacity diagnostics
→ research-integrity analytics
→ evidence retrieval and controlled review
→ explicit certification gates
```

## Implemented surface

### Runtime evidence

- canonical event and causal timestamp contract;
- append-only idempotent file publisher;
- read-only TradeBot runtime event/candidate/market-snapshot tailer;
- optional direct producer bridge;
- standalone JSONL sidecar for legacy or external evidence;
- publisher and source failure accounting;
- deterministic replay, payload hashes and sequence checks;
- session quality, candidate funnel and runtime timeline.

### Market and option analytics

- strict market-tick and option-chain adapters;
- bid/ask and multi-level depth preservation;
- equal- and weighted-constituent breadth;
- contribution concentration;
- futures basis and relative return;
- option spread, microprice and depth imbalance;
- causal lead/lag alignment;
- delta/gamma/theta/vega/residual P&L attribution.

### Profitability realism

- causal ask-entry/bid-exit option outcomes;
- effective-dated, externally supplied cost schedules;
- depth consumption and quantity-capacity curves;
- empirically calibrated queue-fill buckets;
- fitted square-root market-impact coefficient;
- selected-contract and rejected-candidate counterfactuals;
- blocker value: profits missed versus losses avoided.

### Research integrity

- live/replay/backtest feature hashes and parity reports;
- purged and embargoed time-series splits;
- probabilistic and Deflated Sharpe calculations;
- combinatorially symmetric PBO estimate;
- baseline incremental-return comparison;
- PSI, KS, Jensen-Shannon, z-score OOD and CUSUM metrics;
- seeded session/block-bootstrap risk-of-ruin simulation;
- deterministic strategy certification gates.

### CAS, Market Event Graph, RAG and review

- expiry/non-expiry CAS session accumulator;
- evidence-gated directional-testing readiness;
- causal Market Event Graph DAG and lead times;
- deterministic JSON/Markdown/text evidence chunking;
- structured-query versus hybrid-RAG routing;
- controlled analyst/critic workflow;
- optional lazy LangGraph graph with no hardcoded model;
- read-only Streamlit dashboard;
- multi-session campaign aggregation.

## Runtime transport modes

Use exactly one transport per run.

### 1. Built-in read-only tailer

```bash
export AIXION_INTELLIGENCE_ENABLED=1
export AIXION_INTELLIGENCE_OBSERVATION_MODE=SHADOW
export AIXION_INTELLIGENCE_POLL_SEC=1
export AIXION_INTELLIGENCE_OUTPUT_ROOT=.runtime/aixion_trade_intelligence/evidence
export AIXION_INTELLIGENCE_SESSION_ID=<explicit-session-id>
export AIXION_INTELLIGENCE_RUN_ID=<explicit-run-id>
unset AIXION_INTELLIGENCE_DIRECT_BRIDGE_ENABLED
```

The tailer starts from `core.runtime_guard`, reads existing TradeBot evidence
files, and writes a separate canonical stream. Any tailer failure is isolated
from TradeBot startup and execution.

### 2. Direct producer bridge

```bash
export AIXION_INTELLIGENCE_ENABLED=1
export AIXION_INTELLIGENCE_DIRECT_BRIDGE_ENABLED=1
export EXECUTION_MODE=PAPER
export AIXION_INTELLIGENCE_SESSION_ID=<explicit-session-id>
export AIXION_INTELLIGENCE_RUN_ID=<explicit-run-id>
```

This bridge is an opt-in API for authoritative producers. When the direct flag
is set, the runtime guard does not start the file tailer.

### 3. Standalone sidecar

```bash
python scripts/run_aixion_trade_intelligence_sidecar.py \
  --config /path/to/sidecar.json \
  --evidence-root .runtime/aixion_trade_intelligence/evidence
```

Do not run the standalone sidecar over the same sources while the built-in
tailer is enabled.

## Premarket readiness

```bash
python scripts/check_aixion_trade_intelligence_canary.py \
  --config /path/to/aixion_canary.json \
  --output .runtime/aixion_trade_intelligence/canary_readiness.json
```

The result must be `READY_FOR_READ_ONLY_CANARY`. Live execution mode is refused.
Storage requirements and safety factors must be supplied from measured capture
sizes, not generic defaults.

## Post-session report

```bash
python scripts/run_aixion_trade_intelligence_offline.py \
  --event-log .runtime/aixion_trade_intelligence/evidence/<SESSION>/events.jsonl \
  --output-dir .runtime/aixion_trade_intelligence/reports/<SESSION>
```

## RAG ingestion

```bash
python scripts/ingest_aixion_evidence.py \
  report.json report.md strategy_spec.md incident.md \
  --output .runtime/aixion_trade_intelligence/evidence_chunks.jsonl \
  --max-characters-per-chunk <explicit-size>
```

Numeric questions must use structured analytics. RAG is for history,
explanations, similar incidents and document evidence.

## Multi-session campaign

```bash
python scripts/build_aixion_campaign.py reports/*/session_analysis.json \
  --output .runtime/aixion_trade_intelligence/campaign.json \
  --minimum-valid-sessions <registered-minimum> \
  --minimum-expiry-sessions <registered-minimum> \
  --minimum-non-expiry-sessions <registered-minimum> \
  --require-all-diagnosis-ready \
  --require-live-shadow-for-all-valid
```

The minimums are research-plan inputs. They are not hidden inside code.

## Dashboard

```bash
streamlit run scripts/run_aixion_trade_intelligence_dashboard.py -- \
  --session-report /path/to/session_analysis.json \
  --campaign-report /path/to/campaign.json
```

## Evidence that cannot be manufactured offline

The code and synthetic fixtures can validate algorithms, contracts and failure
behavior. These gates remain `NOT_EVALUATED` until real evidence exists:

- queue-fill calibration against observed orders/fills;
- market-impact coefficient and capacity at intended quantities;
- authoritative Indian charge schedule for each effective date;
- live/replay/backtest parity on the same production feature package;
- real rejected-candidate counterfactuals;
- multi-session CAS evidence;
- drift and OOD reference distributions;
- risk of ruin from a sufficient session-level return history;
- holdout profitability;
- live-shadow consistency;
- strategy edge and production promotion readiness.

No LLM, dashboard, positive backtest, or green unit test can override a failed or
unevaluated deterministic gate.

## Safety boundary

- PAPER/SHADOW observation only;
- no broker imports or order calls in the intelligence package;
- no automatic strategy mutation;
- no automatic capital allocation;
- no automatic promotion;
- no LLM in the hot path;
- no profitability guarantee;
- PR remains draft until real canary and repository gates are reviewed.

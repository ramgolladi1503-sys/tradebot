# Tradebot Observability Architecture

Status: planning / architecture contract  
Scope: documentation-only roadmap  
Primary goal: make Tradebot debugging evidence-driven instead of guess-driven.

---

## 1. Why this exists

Tradebot must not be treated as a simple UI that displays rows. The system needs a traceable decision spine that proves how every market cycle, candidate, score, rank, block, fallback state, and execution boundary was reached.

The observability architecture is not meant to create trading edge by itself. It exists to expose whether Tradebot is operating on fresh data, whether fallback data contaminates decisions, whether candidate ranking is meaningful, where latency is introduced, and whether paper/live safety boundaries remain intact.

The architecture must answer these questions quickly:

- Was the feed fresh when the candidate was generated?
- Did the candidate use real quote data or recovered fallback data?
- Where was the candidate generated, normalized, scored, ranked, downgraded, blocked, displayed, or submitted?
- Why was a candidate blocked?
- Why did a candidate become displayable but not executable?
- Which stage created the most latency?
- Did any paper-mode path attempt live-order behavior?
- Did every generated candidate reach a terminal state?

---

## 2. Non-negotiable principles

Observability must be read-only.

It must never:

- allow a trade
- rescue missing data
- hide an exception
- silently fallback
- mutate candidate ranking
- change strategy output
- call broker APIs
- convert advisory candidates into executable candidates
- weaken safety gates

Observability can wrap, measure, log, trace, and summarize behavior. It cannot change trading behavior.

Correct pattern:

```python
with trace_span("candidate.score"):
    score_report = score_candidate(candidate)
```

Wrong pattern:

```python
if tracing_failed:
    allow_trade = True
```

Monitoring failure must never become trading permission.

---

## 3. Architecture target

The final architecture should create a Tradebot Observability Spine:

```text
                      ┌────────────────────┐
                      │   Tradebot Runtime  │
                      └─────────┬──────────┘
                                │
                                ▼
┌────────────┐     ┌────────────────────┐     ┌────────────────────┐
│ Market Feed│ ──▶ │ Decision Pipeline   │ ──▶ │ Candidate / Risk    │
└────────────┘     └────────────────────┘     └────────────────────┘
                                │
                                ▼
                    ┌────────────────────┐
                    │ Observability Spine │
                    │ IDs / events /      │
                    │ traces / metrics /  │
                    │ logs / evidence     │
                    └─────────┬──────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   ┌────────────┐      ┌────────────┐      ┌────────────┐
   │   Tempo    │      │ Prometheus │      │    Loki    │
   │  Traces    │      │  Metrics   │      │    Logs    │
   └────────────┘      └────────────┘      └────────────┘
          └───────────────────┬───────────────────┘
                              ▼
                        ┌──────────┐
                        │ Grafana  │
                        └──────────┘
```

Recommended free stack:

```text
OpenTelemetry Python SDK
→ OpenTelemetry Collector
→ Grafana Tempo or Jaeger for traces
→ Prometheus for metrics
→ Grafana OSS for dashboards
→ Loki for searchable logs
→ Pyroscope later only if profiling is justified
```

Do not start with paid APM tools. The first useful version must be local, free, deterministic, and reviewable.

---

## 4. Mandatory identity contract

Every observable runtime event must carry stable identity.

Required identity fields:

```text
run_id
cycle_id
trace_id
span_id
candidate_id
strategy_id
symbol
instrument_token
execution_mode
```

Candidate events require `candidate_id`.

Cycle events require `cycle_id`.

Blocked, downgraded, rejected, or suppressed events require `reason`.

No critical event may be emitted without `trace_id`.

Example runtime event:

```json
{
  "run_id": "run_20260523_091500",
  "cycle_id": "cycle_20260523_091531_001",
  "trace_id": "trace_cycle_20260523_091531_001",
  "stage": "feed.freshness_check",
  "feed_age_ms": 4200,
  "decision": "blocked",
  "reason": "STALE_FEED"
}
```

Example candidate event:

```json
{
  "candidate_id": "NIFTY_22500_CE_091531",
  "trace_id": "trace_candidate_NIFTY_22500_CE_091531",
  "strategy_id": "nifty_intraday",
  "stage": "candidate.rank",
  "score": 0.78,
  "rank": 1,
  "fallback_state": "none",
  "execution_mode": "paper"
}
```

---

## 5. Candidate decision graph

Tradebot must trace candidate movement, not only function calls.

Target flow:

```text
Market Data
   ↓
Freshness Gate
   ↓
Option Chain Resolver
   ↓
Strategy Signal
   ↓
Candidate Pool
   ↓
Normalization
   ↓
Scoring
   ↓
Ranking
   ↓
Risk Gate
   ↓
Review Queue
   ↓
Paper Execution / Dashboard
```

Each stage must emit one or more of:

```text
entered
passed
blocked
downgraded
fallback_used
latency_ms
reason
```

Good candidate example:

```text
REAL_QUOTE
→ FRESH
→ LIQUID
→ STRATEGY_SIGNAL_VALID
→ SCORE_0.82
→ RANK_1
→ RISK_ALLOWED
→ PAPER_READY
```

Bad candidate example:

```text
MISSING_QUOTE
→ FALLBACK_RECOVERED
→ SCORE_0.46
→ DISPLAYABLE_ONLY
→ EXECUTION_BLOCKED
```

Fallback-driven executable decisions are unsafe. Fallback data may support advisory/debug visibility, but must not make a candidate executable.

---

## 6. Telemetry separation

Do not dump everything into logs.

| Type | Purpose | Tool |
| --- | --- | --- |
| Traces | Follow one cycle or candidate end-to-end | OpenTelemetry + Tempo/Jaeger |
| Metrics | Count and measure system health | Prometheus |
| Logs | Search exact event details | Loki |
| Evidence files | Audit-ready JSON summaries | Runtime evidence artifacts |

Trace answers:

```text
Why did this candidate follow this path?
```

Metric answers:

```text
How often did this condition happen?
```

Log answers:

```text
What exact event happened for this trace_id or candidate_id?
```

Evidence answers:

```text
Can a reviewer audit the run without opening Grafana?
```

---

## 7. Core spans

Core OpenTelemetry spans to add after identity and events are stable:

```text
runtime.cycle
feed.ingest_tick
feed.snapshot_build
feed.freshness_check
option_chain.resolve
strategy.generate_candidates
candidate.normalize
candidate.score
candidate.rank
risk.evaluate
dashboard.write_state
dashboard.render
paper.submit
```

Each span should carry relevant attributes:

```text
run_id
cycle_id
trace_id
candidate_id
strategy_name
symbol
instrument_token
quote_source
fallback_state
feed_age_ms
spread_bps
confidence_raw
opportunity_score
rank
decision
block_reason
execution_mode
```

Tracing must be safely disableable. If tracing fails, Tradebot behavior must remain unchanged.

---

## 8. Core metrics

Tradebot needs trading-health metrics first, not generic vanity metrics.

Required metrics:

```text
tradebot_feed_age_ms
tradebot_feed_stale_total
tradebot_candidates_generated_total
tradebot_candidates_blocked_total
tradebot_candidates_ranked_total
tradebot_fallback_candidates_total
tradebot_fallback_executable_total
tradebot_strategy_latency_ms
tradebot_scoring_latency_ms
tradebot_ranking_latency_ms
tradebot_dashboard_write_latency_ms
tradebot_paper_order_attempt_total
tradebot_live_order_attempt_total
```

Non-negotiable safety metric:

```text
tradebot_fallback_executable_total = 0
```

If this value is greater than zero, Tradebot is unsafe.

Useful dashboard panels:

- feed age
- stale cycles
- fallback candidates
- fallback executable candidates
- generated/scored/ranked/blocked/paper-ready funnel
- latency breakdown by stage
- ranking score distribution
- top-1 vs top-5 score gap
- paper order attempts
- live order attempts

---

## 9. Evidence outputs

Every meaningful run should eventually produce reviewable observability evidence.

Target files:

```text
runtime/evidence/observability_summary.json
runtime/evidence/candidate_decision_funnel.json
runtime/evidence/fallback_safety_report.json
runtime/evidence/feed_freshness_report.json
runtime/evidence/latency_breakdown.json
```

The evidence should allow a reviewer or agent-review gate to answer:

- Did feed stay fresh?
- Did fallback enter execution?
- Did ranking separate strong and weak trades?
- Did the paper/live boundary hold?
- Where did time go?
- What blocked most candidates?
- Did any candidate disappear without terminal state?

---

## 10. Safety invariants

Tests must fail if any of these conditions occur:

```text
fallback candidate becomes executable
stale feed candidate becomes executable
candidate has no terminal state
blocked candidate has no reason
candidate event has no candidate_id
decision event has no trace_id
paper mode attempts live order
observability wrapper changes business output
```

These invariants matter more than dashboards.

A beautiful Grafana dashboard over unsafe decisions is decoration on a broken system.

---

## 11. PR roadmap

This roadmap must be implemented as small focused PRs. Do not combine everything into one giant observability PR.

### PR-OBS-00 — Observability Architecture Contract

Purpose: lock the architecture before coding.

Adds:

```text
docs/observability/OBSERVABILITY_ARCHITECTURE.md
```

Defines:

```text
trace_id
run_id
cycle_id
candidate_id
stage
decision
reason
latency_ms
fallback_state
feed_age_ms
execution_mode
```

Acceptance proof:

```text
Architecture doc explains what is traced, measured, logged, and stored as evidence.
Architecture doc states what observability must never change.
No production behavior changes.
```

Do not touch:

```text
strategy logic
ranking logic
execution logic
broker adapters
dashboard UI
```

---

### PR-OBS-01 — Observability Identity Contract

Purpose: every runtime cycle and every candidate must have stable identity.

Adds:

```text
core/observability/__init__.py
core/observability/ids.py
core/observability/context.py
tests/test_observability_ids.py
```

Implements:

```text
run_id
cycle_id
trace_id
candidate_id
span_id
```

Acceptance proof:

```text
Every cycle gets cycle_id.
Every candidate gets candidate_id.
IDs are deterministic where required.
No behavior change.
```

---

### PR-OBS-02 — Structured Decision Event Schema

Purpose: standardize how Tradebot records decisions.

Adds:

```text
core/observability/events.py
tests/test_observability_events.py
docs/observability/EVENT_SCHEMA.md
```

Required event shape:

```json
{
  "event": "candidate.blocked",
  "run_id": "run_...",
  "cycle_id": "cycle_...",
  "trace_id": "trace_...",
  "candidate_id": "NIFTY_22500_CE",
  "stage": "risk.evaluate",
  "decision": "blocked",
  "reason": "FALLBACK_NOT_EXECUTABLE",
  "latency_ms": 12,
  "fallback_state": "recovered_fallback",
  "execution_mode": "paper"
}
```

Acceptance proof:

```text
Events validate required fields.
Missing trace_id fails.
miss_ing candidate_id fails for candidate events.
miss_ing reason fails for blocked/downgraded events.
```

---

### PR-OBS-03 — Structured JSON Logging Adapter

Purpose: make logs searchable and consistent.

Adds:

```text
core/observability/logging.py
tests/test_observability_logging.py
```

Behavior:

```text
emit_decision_event(event)
emit_runtime_event(event)
emit_safety_event(event)
```

Acceptance proof:

```text
Logs are valid JSON.
Every event has trace_id.
Candidate logs have candidate_id.
Blocked events have reason.
```

---

### PR-OBS-04 — Runtime Cycle Instrumentation

Purpose: trace one full runtime loop.

Instrument:

```text
runtime.cycle.start
runtime.cycle.end
feed.snapshot_loaded
option_chain.loaded
strategy_batch.started
strategy_batch.finished
dashboard_state.written
```

Acceptance proof:

```text
One run produces cycle-level events.
Cycle has start and end timestamps.
Cycle latency is measurable.
No strategy behavior changes.
```

---

### PR-OBS-05 — Candidate Lifecycle Decision Events

Purpose: track every candidate from birth to terminal state.

Stages:

```text
candidate.generated
candidate.normalized
candidate.scored
candidate.ranked
candidate.downgraded
candidate.blocked
candidate.displayed
candidate.paper_ready
candidate.paper_submitted
```

Terminal states:

```text
ranked
blocked
downgraded
displayed
paper_ready
paper_submitted
ignored_with_reason
```

Acceptance proof:

```text
A generated candidate has complete lifecycle evidence.
Blocked candidates still appear in evidence.
No silent drops.
```

---

### PR-OBS-06 — Feed Freshness and Fallback Safety Events

Purpose: make stale feed and fallback contamination impossible to hide.

Adds events:

```text
feed.fresh
feed.stale
quote.real
quote.missing
quote.fallback_used
execution.blocked_fallback
execution.blocked_stale_feed
```

Hard invariant:

```text
fallback_state = recovered_fallback AND decision = executable must fail tests
```

Acceptance proof:

```text
Fallback candidates can be advisory/displayable.
Fallback candidates cannot be executable.
Stale feed candidates cannot be executable.
Tests prove both.
```

---

### PR-OBS-07 — OpenTelemetry Tracing Integration

Purpose: add actual trace spans after IDs and events are stable.

Adds:

```text
core/observability/tracing.py
tests/test_observability_tracing.py
```

Spans:

```text
runtime.cycle
feed.snapshot_build
feed.freshness_check
option_chain.resolve
strategy.generate_candidates
candidate.normalize
candidate.score
candidate.rank
risk.evaluate
dashboard.write_state
paper.submit
```

Acceptance proof:

```text
Tracing can be disabled safely.
Tracing failure does not affect trading behavior.
Spans contain trace_id, cycle_id, and candidate_id where applicable.
```

---

### PR-OBS-08 — Prometheus Metrics Export

Purpose: make Tradebot health measurable.

Adds:

```text
core/observability/metrics.py
scripts/run_metrics_server.py
tests/test_observability_metrics.py
```

Metrics:

```text
tradebot_feed_age_ms
tradebot_feed_stale_total
tradebot_candidates_generated_total
tradebot_candidates_ranked_total
tradebot_candidates_blocked_total
tradebot_fallback_candidates_total
tradebot_fallback_executable_total
tradebot_strategy_latency_ms
tradebot_scoring_latency_ms
tradebot_ranking_latency_ms
tradebot_dashboard_write_latency_ms
tradebot_paper_order_attempt_total
tradebot_live_order_attempt_total
```

Acceptance proof:

```text
Metrics endpoint exposes expected metrics.
Fallback executable count is tracked.
Feed age is tracked.
Block reasons are counted.
```

---

### PR-OBS-09 — Local Free Observability Stack

Purpose: add local stack, not paid tools.

Adds:

```text
docker-compose.observability.yml
observability/otel-collector-config.yaml
observability/prometheus.yml
observability/grafana/provisioning/
docs/observability/LOCAL_OBSERVABILITY_SETUP.md
```

Stack:

```text
OpenTelemetry Collector
Prometheus
Grafana
Tempo or Jaeger
```

Acceptance proof:

```text
docker compose starts local stack.
Prometheus scrapes Tradebot metrics.
Traces are visible in Tempo/Jaeger.
No cloud dependency.
No paid dependency.
```

---

### PR-OBS-10 — Grafana Dashboard Provisioning

Purpose: add useful dashboards only after metrics exist.

Dashboards:

```text
Feed Freshness
Fallback Safety
Candidate Funnel
Ranking Quality
Latency Breakdown
Execution Safety
```

Acceptance proof:

```text
Dashboards are provisioned from JSON.
No manual dashboard setup required.
Fallback executable panel exists.
Feed freshness panel exists.
Candidate funnel exists.
```

Do not build dashboards before metrics. Dashboard-first creates false confidence.

---

### PR-OBS-11 — Loki Log Correlation

Purpose: search logs by trace and candidate.

Adds:

```text
observability/loki-config.yaml
observability/promtail-config.yaml or OTEL log pipeline
docs/observability/LOG_CORRELATION.md
```

Search keys:

```text
trace_id
candidate_id
cycle_id
run_id
strategy_id
block_reason
fallback_state
execution_mode
```

Acceptance proof:

```text
Given a trace_id, matching logs can be found.
Given a candidate_id, full decision history can be found.
Logs correlate with traces.
```

---

### PR-OBS-12 — Observability Evidence Bundle

Purpose: make observability usable even without opening Grafana.

Adds:

```text
runtime/evidence/observability_summary.json
runtime/evidence/candidate_decision_funnel.json
runtime/evidence/fallback_safety_report.json
runtime/evidence/feed_freshness_report.json
runtime/evidence/latency_breakdown.json
```

Acceptance proof:

```text
Run creates observability evidence files.
Evidence files are deterministic.
Evidence files are reviewable by agents.
CI can validate evidence schema.
```

---

### PR-OBS-13 — Safety Invariant Test Suite

Purpose: convert observability into hard safety gates.

Tests must fail if:

```text
fallback candidate becomes executable
stale feed candidate becomes executable
candidate has no terminal state
blocked candidate has no reason
candidate event has no candidate_id
decision event has no trace_id
paper mode attempts live order
observability wrapper changes business output
```

Adds:

```text
tests/observability/test_safety_invariants.py
tests/observability/test_candidate_lifecycle_contract.py
tests/observability/test_fallback_execution_block.py
tests/observability/test_stale_feed_execution_block.py
```

Acceptance proof:

```text
Negative tests exist.
Unsafe states fail closed.
Observability remains read-only.
```

---

### PR-OBS-14 — Trace Replay CLI

Purpose: debug one candidate or cycle from evidence.

Adds:

```text
scripts/replay_trace.py
tests/test_replay_trace.py
docs/observability/TRACE_REPLAY.md
```

Commands:

```bash
python scripts/replay_trace.py --trace-id trace_123
python scripts/replay_trace.py --candidate-id NIFTY_22500_CE_091531
python scripts/replay_trace.py --cycle-id cycle_20260523_091531
```

Acceptance proof:

```text
Can replay candidate decision path.
Can replay blocked candidate.
Can replay stale-feed cycle.
```

---

### PR-OBS-15 — Pyroscope Profiling Later

Purpose: add CPU/memory profiling only if latency remains unexplained.

Do not do this early.

Use only after:

```text
Metrics show latency problem.
Tracing shows stage-level bottleneck.
Code-level hotspot is still unclear.
```

Acceptance proof:

```text
Profiling can be enabled and disabled.
No performance overhead by default.
No effect on trading decisions.
```

---

## 12. Correct implementation order

```text
PR-OBS-00  Observability Architecture Contract
PR-OBS-01  Identity Contract
PR-OBS-02  Event Schema
PR-OBS-03  JSON Logging
PR-OBS-04  Runtime Cycle Instrumentation
PR-OBS-05  Candidate Lifecycle Events
PR-OBS-06  Feed/Fallback Safety Events
PR-OBS-07  OpenTelemetry Tracing
PR-OBS-08  Prometheus Metrics
PR-OBS-09  Local Free Stack
PR-OBS-10  Grafana Dashboards
PR-OBS-11  Loki Log Correlation
PR-OBS-12  Evidence Bundle
PR-OBS-13  Safety Invariant Tests
PR-OBS-14  Trace Replay CLI
PR-OBS-15  Pyroscope Profiling Later
```

---

## 13. What is intentionally out of scope

Do not add these in this roadmap:

```text
Kubernetes monitoring
service mesh
paid Datadog/New Relic
ML anomaly detection
auto-remediation
auto-trade correction
dashboard before metrics
tracing every raw tick
logging full option-chain payloads
```

These are distractions at the current maturity level.

---

## 14. Definition of done for the full roadmap

The roadmap is complete only when Tradebot can prove:

```text
Every cycle is traceable.
Every candidate is traceable.
Every block has a reason.
Every fallback is visible.
Every executable decision is provable.
Every latency bottleneck has a stage.
Every run leaves evidence.
Fallback candidates cannot become executable.
Stale-feed candidates cannot become executable.
Paper mode cannot accidentally cross into live order behavior.
```

If these are not true, the system still has observability theater, not observability architecture.

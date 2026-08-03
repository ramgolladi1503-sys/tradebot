# TradeBot AI Reliability and Decision-Analytics Agent V1

**Status:** Implemented on `feature/ai-pipeline-reliability-agent-v1`
**Component certification:** `SIMULATION_CERTIFIED`
**Live certification:** `LIVE_CERTIFICATION_PENDING`
**Order authority:** None
**Broker-write authority:** None

## 1. Executive definition

The TradeBot AI Reliability and Decision-Analytics Agent is a bounded, evidence-driven software agent that observes TradeBot runtime artifacts, chooses from an allow-listed set of diagnostic tools, forms testable reliability hypotheses, submits machine-checkable findings, and produces post-market candidate and trade analytics.

It is not a trading strategy, signal generator, execution engine, autonomous repair bot, or profitability oracle. It cannot place, modify, or cancel orders. It cannot alter strategy thresholds, ranking weights, risk rules, broker configuration, or live TradeBot decisions.

The agent exists to answer two questions:

1. **Did TradeBot operate truthfully and traceably during the session?**
2. **What happened to every observed candidate, and what evidence-supported lessons are available after the market closed?**

The core safety rule is:

> Model text is untrusted. A deterministic factual finding becomes confirmed only when its evidence identifiers exist and its assertions pass deterministic verification.

## 2. Problem statement

A conventional audit repeatedly inspects source code and finds more theoretical improvements. That creates an indefinite audit loop without proving whether the live pipeline behaved correctly.

TradeBot instead needs an operational observer that follows the real runtime path:

```text
authentication
→ broker/session readiness
→ feed transport
→ per-instrument freshness
→ market state and regime
→ strategy evaluation
→ candidate generation
→ Phase 1
→ Trade Builder
→ Phase 2
→ ranking
→ approval/display
→ execution/fill
→ outcome
```

The observer must distinguish:

- a valid no-trade market from a broken data pipeline;
- an intentionally rejected candidate from a silently lost candidate;
- a real executed outcome from a paper or counterfactual outcome;
- a good decision with a bad outcome from a bad decision that happened to win;
- deterministic evidence from statistical association and narrative hypothesis;
- an operationally truthful pipeline from a profitable strategy.

## 3. Goals

The V1 agent shall:

1. Consume existing TradeBot runtime evidence rather than duplicate the pipeline.
2. Maintain an append-only, redacted, SHA-256 chained evidence ledger.
3. Wake on deterministic anomalies or an explicit operator objective.
4. Select only registered diagnostic tools.
5. Enforce a step budget and tool-call budget.
6. Block all non-read-only tools during `LIVE_OBSERVE`.
7. Require evidence IDs for findings.
8. Require machine assertions for deterministic facts.
9. Reject contradicted or unsupported factual findings.
10. Persist both confirmed and rejected findings.
11. Produce candidate-lineage, rejection, ranking, outcome, and segment analytics.
12. Keep actual, hypothetical, counterfactual, and unresolved outcomes separate.
13. Produce explicit session verdicts and certification levels.
14. Fail closed when selected candidates use stale, fallback, or recovered-fallback truth.
15. State limitations instead of inventing causal explanations.

## 4. Non-goals

V1 shall not:

- place, modify, or cancel broker orders;
- reconnect the broker or feed automatically;
- restart TradeBot automatically;
- alter production source code during a live session;
- change strategy thresholds, feature definitions, ranking weights, or risk limits;
- promote a rejected candidate;
- suppress an approved candidate;
- certify profitability or structural market edge;
- claim a unique cause for a winning or losing trade;
- learn production rules from one trade or one session;
- merge or deploy repairs automatically;
- represent a model-generated sentence as verified evidence.

## 5. Exact definitions

### 5.1 Agent

A bounded control loop that receives an objective and observations, chooses a registered tool or proposes a finding, and terminates under explicit stop and budget conditions.

A log summarizer is not an agent. The implemented system qualifies because it chooses diagnostic tools, maintains state, submits assertions, receives deterministic verification, and stops under bounded rules.

### 5.2 Deterministic trigger

A trigger produced by code without model interpretation. Examples:

- candidate-lineage artifact missing;
- invalid JSON in candidate lineage;
- selected candidate marked stale, fallback, or recovered fallback;
- blocked candidate with no reason.

The model does not decide whether these trigger conditions exist.

### 5.3 Tool

A named, allow-listed callable with:

- a stable name;
- a description;
- structured arguments;
- structured output;
- a declared `read_only` property.

Unknown tools fail with `UNKNOWN_TOOL`. A registered write tool invoked during `LIVE_OBSERVE` fails with `LIVE_MODE_WRITE_TOOL_BLOCKED`.

### 5.4 Evidence

A redacted structured payload persisted to the evidence ledger with:

- `evidence_id`;
- `session_id`;
- event type;
- UTC creation timestamp;
- prior-row SHA-256;
- current-row SHA-256;
- payload.

Evidence is immutable by convention and tamper-evident by verification.

### 5.5 Assertion

A machine-evaluable statement over an evidence payload:

```json
{
  "evidence_id": "EV-...",
  "path": "payload.stale",
  "operator": "eq",
  "expected": true
}
```

Supported operators:

- `eq`, `ne`;
- `gt`, `ge`, `lt`, `le`;
- `contains`, `not_contains`;
- `truthy`;
- `is_none`.

### 5.6 Finding

A proposed conclusion containing:

- title;
- affected stage;
- severity;
- claim kind;
- narrative;
- assertions;
- evidence IDs;
- business effect;
- recommended action;
- confidence.

### 5.7 Confirmed finding

A finding whose evidence IDs exist and whose required assertions all pass deterministic verification.

### 5.8 Rejected finding

A finding with contradictory assertions, missing paths, unknown operators, or failed comparisons.

### 5.9 Insufficient-evidence finding

A proposal that lacks evidence identifiers, references missing evidence, or describes a deterministic fact without assertions.

### 5.10 Candidate lineage

The ordered set of records sharing a stable candidate identity across generation, gates, ranking, approval, execution, and outcome.

### 5.11 Actual outcome

An outcome joined to a real trade-log or execution record. It is labeled `ACTUAL`.

### 5.12 Hypothetical outcome

A shadow outcome for an approved candidate that was not executed. It is labeled `HYPOTHETICAL` and never counted as realized trading performance.

### 5.13 Counterfactual outcome

A shadow outcome for a rejected or blocked candidate. It is labeled `COUNTERFACTUAL` and never counted as a real trade.

### 5.14 Unresolved outcome

A candidate without a terminal or usable shadow outcome. It is labeled `UNRESOLVED`.

### 5.15 Decision quality

Whether the approval was defensible using information available at entry. Degraded truth, stale quotes, failed execution truth, or failed liquidity can make a decision invalid even when the later outcome wins.

### 5.16 Outcome quality

Whether the candidate hit target, stop, time exit, manual exit, or remained unresolved.

### 5.17 Decision/outcome classification

Approved candidates may be classified as:

- `GOOD_DECISION_GOOD_OUTCOME`;
- `GOOD_DECISION_BAD_OUTCOME`;
- `BAD_DECISION_GOOD_OUTCOME`;
- `BAD_DECISION_BAD_OUTCOME`;
- `UNVERIFIABLE`.

Rejected candidates do not receive a fabricated decision-quality score. They use rejection verdicts.

### 5.18 Rejection verdict

- `CORRECT_REJECTION`: available evidence indicates the gate protected against a bad or non-executable outcome.
- `MISSED_OPPORTUNITY`: the candidate later became executable or has explicit net-positive counterfactual evidence.
- `NEUTRAL_REJECTION`: no material target/stop conclusion.
- `INVALID_REJECTION`: rejection contract or reason evidence was invalid.
- `UNVERIFIABLE`: later movement exists but executability or cost evidence is insufficient.

A rejected candidate that later touches a theoretical target is not automatically a missed opportunity.

### 5.19 Claim kind

- `DETERMINISTIC_FACT`: directly machine-verifiable from recorded evidence.
- `STATISTICAL_ASSOCIATION`: relationship observed across data, not unique causality.
- `LIKELY_CONTRIBUTOR`: evidence-supported contributor with uncertainty.
- `UNVERIFIED_HYPOTHESIS`: possible explanation requiring further research.

### 5.20 Severity

- `P0`: false executable emission, unsafe action, or decision using invalid truth.
- `P1`: silent data failure, lineage corruption, unexplained loss, or materially wrong decision contract.
- `P2`: degradation, latency, or incomplete observability.
- `P3`: naming, duplication, style, or non-blocking refactoring.

Only P0 and P1 are live-certification blockers.

### 5.21 Session verdict

Exactly one of:

- `PIPELINE_TRUTHFUL_AND_OPERATIONAL`;
- `PIPELINE_OPERATIONAL_BUT_OBSERVABILITY_INCOMPLETE`;
- `PIPELINE_SUPPRESSED_VALID_CANDIDATES`;
- `PIPELINE_EMITTED_UNTRUSTWORTHY_CANDIDATES`;
- `LIVE_SESSION_INVALID`.

### 5.22 Certification level

- `NOT_CERTIFIED`;
- `COMPONENT_CERTIFIED`;
- `SIMULATION_CERTIFIED`;
- `LIVE_CERTIFICATION_PENDING`;
- `LIVE_CERTIFIED`.

V1 currently produces `SIMULATION_CERTIFIED` and explicitly keeps live certification pending.

## 6. Architecture

```text
                         TRADEBOT RUNTIME — UNCHANGED
┌──────────────────────────────────────────────────────────────────────┐
│ Auth → Feed → Regime → Strategies → Candidate Pool → Phase 1       │
│      → Trade Builder → Phase 2 → Ranking → Approval → Execution     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ existing events, lineage, summaries,
                                │ trade log and shadow outcomes
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     RUNTIME EVIDENCE ADAPTER                         │
│ read JSONL → validate → join actual trades → assess evidence quality │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  DETERMINISTIC TRIGGER DETECTOR                      │
│ missing lineage / invalid rows / degraded selection / missing reason│
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      LIVE AGENT SUPERVISOR                           │
│ deduplicate triggers → create objective → invoke bounded agent       │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       RELIABILITY AGENT                              │
│ observe → choose tool → inspect → propose assertions → stop          │
└───────────────┬─────────────────────────────────────┬────────────────┘
                ▼                                     ▼
┌──────────────────────────────┐       ┌───────────────────────────────┐
│ READ-ONLY DIAGNOSTIC TOOLS   │       │ DETERMINISTIC VERIFIER        │
│ health / analytics / lineage │       │ evidence exists + assertions  │
│ runtime events               │       │ pass, reject, or insufficient │
└───────────────┬──────────────┘       └──────────────┬────────────────┘
                └───────────────────┬─────────────────┘
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  REDACTED HASH-CHAIN EVIDENCE LEDGER                 │
└───────────────────────────────────┬──────────────────────────────────┘
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│              POST-MARKET ANALYTICS AND CERTIFICATION                 │
│ funnel / rejections / autopsies / calibration / verdict / reports    │
└──────────────────────────────────────────────────────────────────────┘
```

## 7. Component design

### 7.1 Contracts module

`core/ai_reliability_agent/contracts.py` defines all enums and immutable dataclasses. Model output is converted into these contracts before the runtime accepts it.

### 7.2 Evidence ledger

`core/ai_reliability_agent/evidence.py` provides:

- canonical JSON serialization;
- recursive key and value redaction;
- thread-safe append;
- per-row UUID evidence identity;
- prior-hash chaining;
- current-row SHA-256;
- flush and best-effort `fsync`;
- chain verification;
- evidence lookup and required-ID checks.

Sensitive key matching includes tokens, API keys, authorization, passwords, client secrets, refresh tokens, and OpenAI API keys. Secret-shaped text such as OpenAI key prefixes and bearer tokens is redacted.

### 7.3 Tool registry

`core/ai_reliability_agent/agent.py` exposes a registry with explicit read-only metadata. The registry is the only path from the reasoner to runtime diagnostics.

### 7.4 OpenAI reasoner

`core/ai_reliability_agent/openai_reasoner.py`:

- uses the Responses API;
- sends `store: false`;
- requests a strict JSON-schema response;
- permits only `TOOL`, `PROPOSE_FINDING`, or `STOP` actions;
- keeps the API key in the HTTP authorization header;
- never treats generated narrative as evidence;
- forbids order, broker-write, threshold, restart, patch, merge, deployment, profitability, and unsupported-causality actions in its system contract.

The model is an investigator, not the verifier.

### 7.5 Reliability agent loop

`ReliabilityAgent` maintains:

- session ID;
- operating mode;
- objective;
- initial observations;
- tool schemas;
- recent tool results;
- confirmed findings;
- rejected findings;
- step count;
- tool-call count.

Stop conditions:

- model emits `STOP`;
- scripted reasoner exhausts actions;
- step budget exhausted;
- tool budget exhausted;
- malformed action;
- missing tool request or finding payload;
- unsupported action.

### 7.6 Assertion verifier

The verifier:

1. requires evidence IDs;
2. confirms all referenced IDs exist;
3. requires assertions for deterministic facts;
4. resolves assertion paths from evidence payloads;
5. applies allow-listed operators;
6. confirms only when every assertion passes;
7. rejects contradictions;
8. returns insufficient evidence for missing evidence.

### 7.7 Deterministic trigger detector

`core/ai_reliability_agent/supervisor.py` currently detects:

- `CANDIDATE_LINEAGE_MISSING` — P1;
- `CANDIDATE_LINEAGE_INVALID_JSON` — P1;
- `UNTRUSTWORTHY_EXECUTABLE_CANDIDATE` — P0;
- `BLOCKED_CANDIDATE_WITHOUT_REASON` — P1.

Each trigger has a SHA-256 fingerprint so repeated polling does not repeatedly investigate the same unchanged condition.

### 7.8 Live supervisor

The supervisor:

- creates a read-only session manifest;
- records it in the evidence ledger;
- polls deterministic triggers at a minimum interval of one second;
- defaults to 15 seconds;
- creates a bounded live agent only for unseen triggers;
- persists trigger evidence and investigation output;
- supports a stop file and bounded iteration count;
- does not interact with the broker or execution engine.

### 7.9 Runtime evidence adapter

`core/ai_reliability_agent/runtime.py` consumes the current TradeBot layout:

```text
.runtime/logs/events.jsonl
.runtime/candidate_lineage/candidate_funnel_YYYYMMDD.jsonl
.runtime/candidate_lineage/candidate_funnel_summary_YYYYMMDD.jsonl
.runtime/logs/trade_log.jsonl
```

Actual trade records are joined to candidate lineage using stable candidate, trade, instrument, order, or record identity. Unmatched trade rows are retained and counted as observability gaps; they are not silently discarded.

### 7.10 Post-market analytics

`core/ai_reliability_agent/analytics.py` produces:

- pipeline funnel;
- rejection reason distribution;
- candidate autopsies;
- decision/outcome classes;
- rejection verdicts;
- actual versus counterfactual outcome counts;
- score-band calibration;
- strategy, regime, option type, expiry-context, and time-bucket segments;
- evidence-labeled observed contributors.

### 7.11 Certification harness

`core/ai_reliability_agent/certification.py` executes deterministic certification probes and emits JSON and Markdown evidence.

## 8. Exact tool definitions

### 8.1 `get_artifact_health`

**Purpose:** Verify whether required evidence artifacts exist and capture their size and SHA-256.

**Arguments:** None required.

**Returns:** For each artifact:

- path;
- existence;
- byte size;
- SHA-256 when available.

**Read-only:** Yes.

### 8.2 `analyze_candidate_lineage`

**Purpose:** Load candidate lineage and actual trade-log records, join them, evaluate evidence quality, and produce deterministic analytics.

**Arguments:** None required in V1.

**Returns:**

- candidate count;
- funnel;
- rejection breakdown;
- decision/outcome distribution;
- rejection verdict distribution;
- actual/counterfactual outcomes;
- score calibration;
- segment analytics;
- autopsies;
- merge statistics;
- evidence-quality statistics.

**Read-only:** Yes.

### 8.3 `query_candidate_lineage`

**Purpose:** Return all available lineage and joined trade-log rows for one candidate.

**Arguments:**

```json
{"candidate_id": "..."}
```

**Returns:**

- candidate ID;
- row count;
- ordered rows;
- trade-lineage merge statistics.

**Read-only:** Yes.

### 8.4 `query_runtime_events`

**Purpose:** Read a bounded tail of runtime events, optionally filtered by event type.

**Arguments:**

```json
{"event_type": "optional", "limit": 100}
```

Limit is clamped between 1 and 500.

**Read-only:** Yes.

## 9. Operating modes

### 9.1 `LIVE_OBSERVE`

Permitted:

- read artifact health;
- inspect candidate lineage;
- inspect runtime events;
- calculate deterministic analytics;
- propose evidence-backed findings;
- persist evidence and reports.

Forbidden:

- broker writes;
- orders;
- restarts;
- code changes;
- threshold changes;
- candidate promotion or suppression;
- deployment.

### 9.2 `POST_MARKET_ANALYZE`

Permitted:

- join actual trade outcomes;
- run candidate autopsies;
- compare approved and rejected cohorts;
- generate reports;
- formulate research hypotheses with explicit epistemic labels.

### 9.3 `REPAIR_PROPOSE`

Reserved for a future isolated repair workflow. It does not grant merge or deployment authority.

### 9.4 `VERIFY`

Reserved for replaying a verified failure and comparing before/after evidence.

## 10. Analytics definitions

### 10.1 Pipeline funnel

Counts rows by stage and status, plus displayable, rankable, executable, and top-opportunity flags.

### 10.2 Rejection breakdown

Counts stable rejection codes, preferring reason codes over free-text descriptions.

### 10.3 Candidate autopsy

For each candidate:

- strategy;
- approval state;
- execution state;
- terminal outcome;
- outcome scope;
- decision/outcome class;
- rejection verdict;
- observed contributors;
- MFE, MAE, and P&L when present;
- data-truth flags;
- evidence identifiers.

### 10.4 Outcome attribution

The agent does not claim an exact market cause. It reports recorded facts and possible contributors using claim kinds.

Supported contributor taxonomy includes:

- `THESIS_INVALIDATED`;
- `LATE_ENTRY`;
- `FALSE_BREAKOUT`;
- `REGIME_TRANSITION`;
- `PARTICIPATION_COLLAPSE`;
- `LEADERSHIP_REVERSAL`;
- `OPTION_UNDERRESPONSE`;
- `IV_CONTRACTION`;
- `THETA_DECAY`;
- `LIQUIDITY_DETERIORATION`;
- `EXCESSIVE_SLIPPAGE`;
- `STOP_TOO_TIGHT`;
- `TARGET_TOO_AMBITIOUS`;
- `DATA_QUALITY_FAILURE`;
- `EXECUTION_FAILURE`;
- `EXTERNAL_EVENT_SHOCK`;
- `NORMAL_VARIANCE`;
- `INSUFFICIENT_EVIDENCE`.

V1 emits only categories supported by available fields. Unavailable evidence produces `INSUFFICIENT_EVIDENCE` rather than a fabricated explanation.

### 10.5 Direction-aware option attribution

IV-contraction attribution requires the underlying to move favorably for the recorded option direction:

- CE / call / `BUY_CALL`: underlying move must be positive;
- PE / put / `BUY_PUT`: underlying move must be negative.

An underlying decline is not considered favorable for a call merely because its absolute magnitude is large.

### 10.6 Rejected-target protection

A theoretical target after rejection is insufficient to claim a missed opportunity. The rejection becomes `MISSED_OPPORTUNITY` only when evidence shows later executability or explicit net-positive counterfactual performance after costs.

### 10.7 Score calibration

Candidates are grouped into score bands:

- `0.00-0.24`;
- `0.25-0.49`;
- `0.50-0.74`;
- `0.75-1.00`;
- `MISSING`.

Each band reports count, known-outcome count, target rate, mean P&L, mean MFE, and mean MAE when available. This reveals whether ranking scores separate outcomes rather than merely decorate rows.

## 11. Evidence-quality gates

The post-market finalizer measures:

- lineage artifact existence;
- trade-log existence;
- summary existence;
- invalid JSON rows;
- blocked rows without reason;
- selected/executed rows without stable identity;
- approved candidates without terminal status;
- unmatched actual trade rows;
- generated candidate count versus distinct lineage IDs;
- unexplained disappearances;
- total observability gaps.

## 12. Hallucination-control design

The system does not promise that a language model can never generate a false sentence. It prevents unsupported model output from becoming a confirmed deterministic finding through these controls:

1. Strict structured action schema.
2. Allow-listed action types.
3. Allow-listed tools.
4. Live write-tool block.
5. Tool and step budgets.
6. Redacted evidence persistence.
7. Required evidence IDs.
8. Required assertions for deterministic facts.
9. Deterministic path/operator evaluation.
10. Persistence of rejected findings.
11. Explicit claim-kind taxonomy.
12. Actual/hypothetical/counterfactual separation.
13. Rejected-target hindsight protection.
14. Direction-aware option attribution.
15. Explicit insufficient-evidence outcomes.

A model recommendation remains advisory. It cannot alter TradeBot runtime behavior.

## 13. Security and privacy

- Secrets are recursively redacted before evidence persistence.
- API keys remain in HTTP headers and are not included in model request bodies or ledgers.
- Responses requests set `store: false`.
- The agent package imports no Kite client, broker client, execution engine, or execution router.
- The agent package contains no order placement, order modification, or cancellation calls.
- The agent package contains no subprocess, shell execution, `eval`, or `exec` capability.
- Runtime artifacts are read locally.

## 14. Integration scope

### Included

- new isolated package under `core/ai_reliability_agent`;
- one CLI entry point;
- consumption of existing event, lineage, summary, and trade logs;
- local read-only diagnostic tools;
- OpenAI reasoner adapter;
- deterministic verifier;
- post-market report generator;
- certification harness;
- focused test suites.

### Deliberately unchanged

- `main.py`;
- `core/orchestrator.py`;
- authentication implementation;
- feed implementation;
- strategy files;
- Trade Builder;
- Phase 1 and Phase 2 logic;
- ranking weights;
- risk engine;
- execution engine/router;
- broker configuration;
- dashboard behavior;
- order authority.

## 15. CLI and runbook

### 15.1 Run component and simulation certification

```bash
PYTHONPATH=. python scripts/run_ai_reliability_agent.py certify \
  --output-dir .runtime/ai_reliability_agent/certification
```

### 15.2 Run one bounded live investigation

```bash
export OPENAI_API_KEY='...'
PYTHONPATH=. python scripts/run_ai_reliability_agent.py live-observe \
  --session-id LIVE-20260731 \
  --repo-root . \
  --evidence-path .runtime/ai_reliability_agent/LIVE-20260731/evidence.jsonl \
  --objective 'Identify the highest-impact evidence-backed reliability issue, or prove that current evidence is insufficient.'
```

### 15.3 Run trigger-driven live supervisor

```bash
PYTHONPATH=. python scripts/run_ai_reliability_agent.py live-watch \
  --session-id LIVE-20260731 \
  --repo-root . \
  --session-date 20260731 \
  --interval-sec 15 \
  --evidence-path .runtime/ai_reliability_agent/LIVE-20260731/evidence.jsonl \
  --stop-file .runtime/ai_reliability_agent/LIVE-20260731/STOP
```

Create the stop file to terminate cleanly:

```bash
touch .runtime/ai_reliability_agent/LIVE-20260731/STOP
```

### 15.4 Generate post-market analytics

```bash
PYTHONPATH=. python scripts/run_ai_reliability_agent.py finalize \
  --session-id LIVE-20260731 \
  --repo-root . \
  --session-date 20260731 \
  --output-dir .runtime/ai_reliability_agent/LIVE-20260731/report
```

## 16. Testing strategy

### 16.1 Evidence and security tests

Cover:

- sensitive-key redaction;
- secret-shaped value redaction;
- safe nested values;
- canonical JSON ordering;
- empty ledger;
- append/get;
- hash linking;
- payload tampering;
- previous-hash tampering;
- invalid JSON;
- missing evidence IDs;
- redaction before storage;
- concurrent appends.

### 16.2 Agent behavior tests

Cover:

- every assertion operator;
- missing evidence;
- missing assertion path;
- unknown operator;
- empty and duplicate tool names;
- unknown tools;
- live write blocking;
- post-market registered write behavior;
- tool exceptions;
- tool execution and stop;
- confirmed finding;
- rejected finding;
- tool budget;
- invalid budget;
- exhausted scripted reasoner.

### 16.3 Analytics tests

Cover:

- outcome normalization;
- decision/outcome classes;
- rejection verdicts;
- session-verdict precedence;
- candidate ordering;
- funnel and reason counts;
- data-quality, participation, liquidity, late-entry, regime, invalidation, IV, and slippage contributors;
- normal-variance and insufficient-evidence fallbacks;
- good/bad decision separation;
- actual/counterfactual separation;
- rejected-target hindsight protection;
- CE/PE direction handling.

### 16.4 Integration and behavioral tests

Cover:

- Responses strict-schema request;
- API-key exclusion from request body;
- missing API key;
- invalid JSON ingestion;
- redacted manifest;
- TradeBot artifact paths;
- tool registration;
- JSON/Markdown finalization;
- missing-lineage invalid session;
- fallback-selected fail-closed verdict;
- epistemic-language report;
- certification harness;
- deterministic triggers;
- supervisor interval limit;
- trade-lineage joins;
- unmatched trade evidence;
- rejected candidate non-promotion;
- disappearance detection;
- actual trade-log outcomes;
- hypothetical and counterfactual scope;
- candidate query including actual trade rows.

Current focused result:

```text
131 passed
Python compilation: PASS
```

## 17. Certification gates

### 17.1 Simulation certification acceptance

The certification harness requires all of:

1. evidence redaction;
2. immutable hash chain;
3. live read-only boundary;
4. supported finding confirmed;
5. unsupported finding rejected;
6. decision/outcome separation;
7. untrustworthy emission fail-closed;
8. outcome-scope separation;
9. rejected-target hindsight protection;
10. direction-aware option attribution.

Current result:

```text
10/10 passed
SIMULATION_CERTIFIED
LIVE_CERTIFICATION_PENDING
```

### 17.2 Live certification acceptance

`LIVE_CERTIFIED` must not be issued until a real market session proves:

1. valid lineage and event artifacts;
2. zero invalid JSON rows;
3. zero selected candidates using stale, fallback, or recovered-fallback truth;
4. zero unexplained candidate disappearances;
5. all blocked candidates have reasons;
6. all selected/executed rows have stable identity;
7. all actual trade rows join to candidate lineage;
8. all approved candidates have terminal or explicitly open status;
9. evidence chain verification passes;
10. TradeBot strategy, risk, ranking, execution, and broker behavior remained unchanged during observation;
11. final verdict is `PIPELINE_TRUTHFUL_AND_OPERATIONAL`.

A single session still does not certify profitability. Operational live certification and strategy evidence certification remain separate.

## 18. Output artifacts

### Live

- session manifest;
- trigger evidence;
- tool-result evidence;
- confirmed findings;
- rejected findings;
- evidence-chain verification result.

### Certification

- `ai_reliability_agent_component_certification.json`;
- `ai_reliability_agent_component_certification.md`.

### Post-market

- `<session_id>_post_market_report.json`;
- `<session_id>_post_market_report.md`.

## 19. QA exit criteria

Component/simulation exit requires:

- focused tests pass;
- Python compilation passes;
- certification gates pass;
- no forbidden execution capability in the agent package;
- generated reports explicitly preserve certification limitations;
- no changes to runtime strategy or execution behavior.

Live exit requires the separate live gates in Section 17.2.

## 20. Known limitations and planned extensions

1. V1 reads current JSONL evidence rather than adding OpenTelemetry spans to every TradeBot stage.
2. Current deterministic triggers cover critical lineage and degraded-selection cases, not every feed/auth SLA.
3. Contributor attribution depends on fields present in lineage and trade records.
4. Score calibration requires enough terminal observations to be meaningful.
5. The verifier validates assertions but does not yet run a separate model-based contradiction search.
6. Multi-session incident memory is not yet promoted into a production knowledge base.
7. Repair proposal and replay verification modes are contract placeholders, not autonomous deployment paths.
8. Live multi-hour stability remains untested until a real market session.

Recommended later work must remain evidence-driven:

- add auth/feed/cycle deterministic triggers using existing runtime health artifacts;
- add completed-bar shadow outcomes at fixed horizons;
- add OpenTelemetry trace correlation where useful;
- add independent replay tools for verified incidents;
- add multi-session cohort analysis with minimum sample gates;
- add human-approved isolated repair branches.

## 21. Interview-ready description

> I designed and implemented a bounded AI reliability agent for a real-time market-data and trade-candidate pipeline. Deterministic triggers wake the agent, an LLM chooses only allow-listed read-only diagnostic tools, and every factual conclusion must reference tamper-evident evidence and pass machine assertions. The system separates actual, hypothetical, and counterfactual trade outcomes, performs post-market candidate autopsies, and blocks unsupported model narratives from becoming confirmed findings. Runtime trading logic and broker execution remain outside the agent’s authority.

## 22. Final truth statement

The agent is implemented and simulation-certified for its defined component scope. It is not hallucination-proof, live-certified, profitable, or production-deployed. Its certified guarantee is narrower and defensible:

> Unsupported model output cannot become a confirmed deterministic finding through the implemented verification path, and the live agent has no registered authority to modify TradeBot or execute broker actions.

# Tradebot Intelligence Layer Architecture

## High-Level Architecture

The Tradebot Intelligence Layer is a read-only system that runs beside Tradebot. It analyzes existing runtime evidence and produces diagnosis, recommendations, issue drafts, memory, and edge-improvement decisions.

```text
Tradebot Runtime
  -> Evidence Sources
  -> Evidence Loader
  -> Evidence Quality Validator
  -> Diagnostic Agents
  -> Agent Orchestrator
  -> RCA Prioritizer
  -> Reports
  -> Issue Drafts
  -> Memory Store
  -> Edge Decision Board
```

The layer must never sit inside the live order path.

## Data Flow

### 1. Tradebot Runtime

Existing Tradebot modules continue to run unchanged. They produce evidence through logs, runtime JSON, analytics files, no-trade artifacts, candidate outputs, ranking outputs, safety evidence, and agent-review documents.

### 2. Evidence Sources

Allowed read-only evidence source families include:

- `.runtime/live_sessions/`
- `runtime/analytics/`
- `logs/`
- `data/`
- `docs/agent_reviews/`
- existing evidence JSON files

Agents must not read arbitrary repository files unless their contract explicitly allows it.

### 3. Evidence Loader

The loader will normalize one market session into a session evidence object. It must preserve raw source references and record missing sources.

### 4. Evidence Quality Validator

The validator will verify timestamps, schema fields, session consistency, stale data, impossible values, and contradictions that block downstream conclusions.

### 5. Diagnostic Agents

Specialized agents analyze a validated session. Each agent has narrow ownership and a contract-defined input/output boundary.

Initial future agents:

- Feed Doctor Agent
- Candidate Flow Agent
- Ranking Quality Agent
- Strategy Edge Agent
- Risk and Safety Boundary Agent
- Evidence Integrity Agent
- Regression Risk Agent

### 6. Agent Orchestrator

The orchestrator runs agents in a deterministic order, gathers findings, downgrades conclusions when evidence quality is weak, and prevents downstream agents from making unsupported claims.

### 7. RCA Prioritizer

The prioritizer converts many findings into one ranked root-cause list.

Default priority order:

1. critical safety issue
2. feed tradability issue
3. evidence contradiction
4. candidate pipeline issue
5. ranking issue
6. strategy edge issue

### 8. Reports

Reports will be written under:

- `.runtime/intelligence/reports/`

Reports must include human-readable Markdown and machine-readable JSON.

### 9. Issue Drafts

Issue drafts will be written under:

- `.runtime/intelligence/github_issue_drafts/`

Initial implementation must produce drafts only. It must not auto-create GitHub issues.

### 10. Memory Store

Cross-session memory will be written under:

- `.runtime/intelligence/memory/`

Memory tracks repeated patterns and prevents overreacting to a single session.

### 11. Edge Decision Board

The final decision board produces one daily decision such as:

- fix feed
- fix candidate flow
- fix ranking
- collect more data
- promote strategy
- suspend strategy
- do nothing

## Read-Only Integration Model

The Intelligence Layer may read existing files and write intelligence artifacts. It may not call Tradebot runtime functions that mutate state.

Allowed:

- read files
- parse logs
- load evidence JSON
- produce reports
- produce issue drafts
- produce memory artifacts

Forbidden:

- broker calls
- live orders
- runtime state mutation
- feed restart
- lock-file mutation
- strategy/ranking/risk threshold mutation
- automatic code changes

## Suggested Future Module Layout

This PR does not create code. Future code may use a structure like:

```text
core/intelligence/
  evidence_registry.py
  session_loader.py
  evidence_quality.py
  agents/
    feed_doctor.py
    candidate_flow.py
    ranking_quality.py
    strategy_edge.py
    risk_safety.py
    evidence_integrity.py
    regression_risk.py
  orchestrator.py
  rca_prioritizer.py
  reports.py
  recommendations.py
  memory.py
scripts/
  run_tradebot_intelligence.py
  watch_tradebot_intelligence.py
```

This layout is illustrative only. No implementation is allowed in the architecture-contract PR.

## Failure Model

### Missing Evidence

Missing evidence must be represented explicitly. It must not be silently ignored.

Example: If ranking evidence is absent, Ranking Quality Agent must return `insufficient evidence`.

### Schema Drift

If a required field changes shape or disappears, the validator must block or downgrade affected conclusions.

### Contradictory Evidence

If one file says quote health is good and another says candidates were rejected for stale quotes, Evidence Integrity Agent must flag the contradiction.

### Stale Evidence

Old files must not be treated as current session truth.

### Unsafe Mode Ambiguity

If LIVE, audit-only, manual-approval, or broker-call evidence is ambiguous, safety status must be `unknown` or `unsafe to conclude`, not assumed safe.

## Ranking and UI Intelligence Concerns

The architecture must explicitly support detecting weak opportunity intelligence:

- confidence score compression
- fallback/recovered data entering displayable or executable paths
- raw emitted rows being shown as if they were ranked opportunities
- executable-only filters hiding upstream quality problems
- BUY-only directional bias
- missing capital allocation intelligence

These concerns are diagnostic targets. They must not be fixed by this architecture PR.

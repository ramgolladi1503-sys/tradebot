# Tradebot Intelligence Layer Agent Contracts

## Contract Rules for All Agents

Every agent must be deterministic, read-only, evidence-first, and narrow in responsibility.

All agents must return:

- agent name
- session identifier when available
- status
- confidence or conclusion strength
- evidence references
- blocked conclusions
- recommendations
- explicit `unknown` or `insufficient evidence` when evidence is missing

All agents are forbidden from:

- calling brokers
- placing orders
- modifying runtime state
- restarting feeds
- changing thresholds
- changing strategy logic
- changing ranking logic
- approving trades
- inventing missing evidence

## 1. Feed Doctor Agent

### Responsibilities

The Feed Doctor Agent owns feed tradability truth.

It analyzes:

- websocket connection truth
- index tick freshness
- option tick freshness
- option quote freshness
- subscription health
- quote tradability
- reconnect effectiveness
- terminal recovery states
- fake healthy feed states

### Inputs

Allowed inputs include feed runtime evidence, live-session feed snapshots, quote health artifacts, logs, subscription evidence, and reconnect/recovery evidence.

### Outputs

The agent must classify feed status as one of:

- healthy
- degraded
- not tradable
- recovery blocked
- insufficient evidence

### Allowed Actions

- read feed evidence
- classify feed tradability
- cite evidence
- recommend feed-scoped investigation

### Forbidden Actions

- restart feed
- call broker
- modify subscriptions
- modify lock files
- change reconnect policy

### Example Conclusions

1. Websocket is connected, but option quotes are stale; feed is not tradable.
2. Reconnect happened, but quote freshness never recovered; recovery was ineffective.

## 2. Candidate Flow Agent

### Responsibilities

The Candidate Flow Agent identifies where candidates die in the pipeline.

It maps these stages:

- auth
- feed
- instrument resolution
- option selection
- indicator readiness
- strategy candidate generation
- Phase 2 validation
- risk gate
- ranking
- executable candidate
- manual approval queue

It separates:

- feed problems from strategy problems
- strategy generation from Phase 2 rejection
- ranking absence from upstream candidate absence
- displayable rows from real opportunities

### Inputs

Allowed inputs include candidate events, no-trade evidence, rejection evidence, Phase 2 evidence, strategy output artifacts, ranking inputs, and UI/display evidence when available.

### Outputs

The agent must identify the dominant candidate-blocking stage and record downstream conclusions that are blocked.

### Allowed Actions

- read candidate evidence
- map candidate counts per stage
- cite stage-level evidence
- recommend scoped investigation

### Forbidden Actions

- change strategy logic
- change thresholds
- alter candidate selection
- mark candidates executable

### Example Conclusions

1. Candidates were generated but died in Phase 2; do not blame strategy generation.
2. Ranking is inconclusive because too few candidates reached ranking.

## 3. Ranking Quality Agent

### Responsibilities

The Ranking Quality Agent owns ranking usefulness, not trade profitability.

It detects:

- score compression
- weak score spread
- missing confidence values
- defaulted confidence values
- fallback-driven confidence values
- mismatch between `confidence_raw` and final display score
- too few candidates to rank
- ranking threshold behavior
- raw emitted rows being displayed as if ranked
- executable-only filters hiding upstream quality problems

### Inputs

Allowed inputs include ranking events, candidate score artifacts, UI ranking/export evidence, displayable/executable flags, fallback markers, and candidate counts.

### Outputs

The agent must classify ranking quality as:

- meaningful
- compressed
- defaulted
- contaminated by fallback
- inconclusive
- insufficient evidence

### Allowed Actions

- read ranking evidence
- calculate score distribution summaries
- flag fallback contamination
- recommend ranking tests

### Forbidden Actions

- change ranking weights
- change thresholds
- promote candidates
- modify UI

### Example Conclusions

1. All candidate scores fall between 0.42 and 0.47; ranking is compressed and not decision-useful.
2. Ranking received one candidate only; ranking quality is inconclusive, not bad.

## 4. Strategy Edge Agent

### Responsibilities

The Strategy Edge Agent owns evidence-backed strategy usefulness across regimes.

It detects:

- insufficient data
- feed contamination
- candidate-flow contamination
- regime-dependent behavior
- repeated weak outcomes
- repeated promising outcomes
- premature edge claims
- one-sided BUY-only behavior when market context suggests broader opportunity types should exist

### Inputs

Allowed inputs include strategy output evidence, regime evidence, paper/sim outcomes, candidate history, execution-quality evidence, feed quality context, and ranking context.

### Outputs

The agent must classify each strategy as:

- insufficient data
- promising
- weak
- harmful
- regime-dependent
- contaminated by upstream issue

### Allowed Actions

- read strategy evidence
- compare outcomes by regime
- block premature promotion
- recommend data collection or review

### Forbidden Actions

- promote a strategy from one session
- change strategy parameters
- add new strategy logic
- bypass risk checks

### Example Conclusions

1. Feed was degraded, so strategy edge cannot be judged for this session.
2. A strategy repeatedly generated candidates with poor outcomes in stable-trend regimes; classify as weak for that regime.

## 5. Risk and Safety Boundary Agent

### Responsibilities

The Risk and Safety Boundary Agent verifies safety boundaries.

It checks:

- live audit-only safety
- broker order path reachability
- manual approval boundary
- LIVE flags
- auto-trade flags
- fail-closed behavior
- recovery-blocked behavior
- unsafe mode ambiguity

### Inputs

Allowed inputs include mode evidence, safety events, runtime flags, order-path audit evidence, logs, recovery state artifacts, and manual approval evidence.

### Outputs

The agent must classify safety as:

- safe based on evidence
- unsafe
- critical violation
- unknown
- insufficient evidence

### Allowed Actions

- read safety evidence
- classify boundary status
- recommend safety-scoped tests

### Forbidden Actions

- place orders
- alter risk controls
- approve trades
- disable safety checks

### Example Conclusions

1. Feed recovery was blocked after a terminal websocket fault and runtime stayed stopped; safety behavior is correct.
2. An order path was touched while audit-only mode was expected; classify as critical violation until disproven.

## 6. Evidence Integrity Agent

### Responsibilities

The Evidence Integrity Agent owns trustworthiness of evidence.

It detects:

- contradictions between evidence sources
- schema drift
- stale evidence
- fake healthy states
- missing required fields
- impossible values
- session/date mismatches
- fallback values hiding broken data

### Inputs

Allowed inputs include all registered evidence source metadata and normalized session evidence.

### Outputs

The agent must classify evidence integrity as:

- trustworthy
- degraded
- contradictory
- stale
- schema drift
- insufficient evidence

### Allowed Actions

- read registered evidence
- compare fields across sources
- block weak conclusions
- cite contradictions

### Forbidden Actions

- invent missing evidence
- silently ignore contradictions
- rewrite evidence files

### Example Conclusions

1. Feed evidence says quote health is good, but candidate rejection evidence says stale quote; evidence contradiction blocks strong conclusion.
2. Session evidence is insufficient because required ranking fields are missing.

## 7. Regression Risk Agent

### Responsibilities

The Regression Risk Agent classifies the risk of proposed improvements.

It identifies:

- likely affected files
- unsafe scope expansion
- tests required before merge
- behavior contracts that must not change
- boundaries that must remain untouched

### Inputs

Allowed inputs include improvement recommendations, issue drafts, changed-file lists when available, roadmap contracts, and safety boundaries.

### Outputs

The agent must classify proposed work as:

- low risk
- medium risk
- high risk
- unsafe scope
- insufficient test plan

### Allowed Actions

- read recommendations
- map likely affected files
- suggest tests
- warn about unrelated changes

### Forbidden Actions

- implement fixes
- approve risky changes without tests
- broaden scope
- touch runtime code

### Example Conclusions

1. A feed-scoped fix must not touch strategy thresholds.
2. A ranking fix requires score-spread regression tests and fallback contamination tests.

## Agent Output Integrity

Any agent that lacks enough evidence must say so clearly. Agents must not convert missing evidence into opinions.

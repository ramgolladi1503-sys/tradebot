# Tradebot Intelligence Layer Bible

## Purpose

The Tradebot Intelligence Layer is a read-only analysis system that sits beside Tradebot and converts runtime evidence into root-cause reports, improvement recommendations, issue drafts, cross-session memory, and edge-improvement decisions.

It exists because Tradebot already emits useful evidence, but the evidence still requires too much manual interpretation. The layer must answer hard questions such as:

- Why did no executable candidates appear today?
- Was the feed actually tradable, or only connected?
- Did candidates die in strategy generation, Phase 2, risk, ranking, or UI display?
- Was ranking meaningful, compressed, defaulted, or inconclusive?
- Are strategy results contaminated by feed or evidence defects?
- Did the bot remain inside LIVE/audit-only/manual-approval safety boundaries?

## Problem It Solves

The current system can produce rows, logs, no-trade reasons, feed evidence, and agent-review artifacts. That is not enough. The Intelligence Layer must turn those artifacts into one dominant truth, with evidence-backed conclusions and scoped next actions.

The layer is designed to detect issues such as:

- connected websocket state that is not tradable quote state
- option quote staleness despite fresh index ticks
- confidence score compression where most candidates look equally weak
- fallback/recovered data being treated as displayable or executable
- strategy-to-UI emission without a true opportunity ranking layer
- executable-only filtering hiding upstream quality problems
- BUY-only candidate behavior that may indicate directional bias
- missing capital allocation or opportunity prioritization intelligence
- contradictory evidence between feed, candidate, no-trade, ranking, and safety files

## What It Is Not

The Intelligence Layer is not:

- a trading strategy
- an order execution engine
- an auto-trading system
- a broker adapter
- a dashboard-first feature
- an automatic code fixer
- an automatic PR merger
- a replacement for manual approval
- a system that can infer truth without evidence

## Read-Only Principle

The layer must read evidence and write intelligence outputs only. It must not mutate Tradebot runtime state.

Allowed outputs include:

- session RCA report
- agent findings
- dominant root causes
- improvement recommendations
- GitHub issue drafts
- cross-session memory
- edge improvement decision board

Forbidden outputs include:

- orders
- broker calls
- feed restarts
- lock-file changes
- strategy threshold changes
- ranking threshold changes
- risk-limit changes
- runtime-state changes

## Evidence-First Principle

Every conclusion must map to evidence. A finding must cite a file, session, timestamp, metric, event, or validated absence of data.

Missing evidence must produce `unknown` or `insufficient evidence`. It must not produce fake certainty.

Two examples:

1. If ranking received only one candidate, the system must say ranking quality is inconclusive, not good or bad.
2. If feed evidence is miss-ing, the system must not infer feed health from candidate absence.

## No-Trading-Action Principle

This system improves engineering quality and trading-edge validation. It does not directly execute trades.

Agents may recommend engineering work. They may not place trades, change strategy parameters, or make live trading decisions.

## Relationship to Tradebot Runtime

Tradebot remains the runtime system. The Intelligence Layer reads runtime evidence produced by Tradebot and writes separate intelligence artifacts under `.runtime/intelligence/`.

The initial integration model is post-session and read-only. Later watch mode may observe files during market hours, but it still must not mutate runtime state.

## Core Outputs

### Session RCA Report

A human-readable and machine-readable explanation of the session, dominant blockers, evidence quality, and next action.

### Agent Findings

Structured findings from specialized agents such as Feed Doctor, Candidate Flow, Ranking Quality, Strategy Edge, Risk and Safety Boundary, Evidence Integrity, and Regression Risk.

### Dominant Root Causes

Prioritized causes that prevent scattered diagnosis. Safety violations outrank feed issues, feed tradability outranks strategy edge, and evidence contradictions block weak conclusions.

### Improvement Recommendations

Scoped engineering recommendations with allowed scope, forbidden scope, evidence references, and suggested tests.

### GitHub Issue Drafts

Paste-ready issue drafts. Initial implementation must not auto-create issues.

### Cross-Session Memory

A record of repeated patterns across market sessions, such as recurring option quote staleness, ranking compression, fallback-driven candidates, or strategy weakness by regime.

### Edge Improvement Decision Board

A final decision layer that says whether to fix feed, fix candidate flow, fix ranking, collect more data, suspend a strategy, promote a strategy, or do nothing.

## Non-Negotiable Truth Rule

The Intelligence Layer must prefer an honest `unknown` over a confident lie.

# Opportunity Engine Roadmap

This roadmap points to the detailed build scope in:

- [Real Opportunity Engine Bible](REAL_OPPORTUNITY_ENGINE_BIBLE.md)
- [Ranking and Opportunity Diagnostics](RANKING_OPPORTUNITY_DIAGNOSTICS.md)
- [Opportunity Diagnostics Evidence](OPPORTUNITY_DIAGNOSTICS_EVIDENCE.md)

## Current position

Completed:

```text
PR #55 — Ranking/opportunity-engine diagnostics
PR #56 — Opportunity diagnostics evidence capture
```

Current planned direction:

```text
PR #57 — Opportunity Engine Scope Bible
PR #58 — Movement Candidate Contract
PR #59 — Movement Regime Classifier v1
PR #60 — Strategy Registry and Candidate Pool Shell
PR #61 — Opening Drive and ORB Retest
PR #62 — Compression Breakout and Trend Pullback
PR #63 — VWAP Reclaim and Failed Breakout Trap
PR #64 — Exhaustion and Mean Reversion Extension
PR #65 — Event Volatility and Late-Day Momentum
PR #66 — Option Pressure Confirmation
PR #67 — No-Trade Engine
PR #68 — Opportunity Ranker v1
PR #69 — Evidence and CLI Integration
PR #70 — Dashboard Separation
```

## Build rule

Do not add strategies directly into execution.

Every strategy must first produce a candidate. Candidate pool, confirmation, blockers, ranker, and execution gate decide what happens next.

## Safety rule

Fallback quote data, stale option LTP, missing depth, and wide spread must never become executable truth.

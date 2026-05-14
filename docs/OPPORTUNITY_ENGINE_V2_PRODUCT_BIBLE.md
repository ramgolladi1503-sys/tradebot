# Opportunity Engine V2 Product Bible

## 1. Purpose

Opportunity Engine V2 is the rebuild path for Tradebot's decision brain. It must convert raw market observations and strategy outputs into ranked, explainable, data-quality-safe trading opportunities.

This is not a cosmetic dashboard rebuild. The goal is to replace the current filtered-output-viewer behavior with a proper decision system that can answer four questions before any trade is considered:

1. Is the market data real and fresh?
2. Is this candidate structurally valid?
3. Why is this opportunity ranked above others?
4. Is it safe to execute now, and at what size?

Tradebot remains a QA/SDET + fintech reliability project. This document does not claim trading profitability. It defines the engineering standard required before a candidate can be trusted by the app.

---

## 2. Core Problem Statement

The current system can produce rows, but rows are not opportunities.

The V1 failure pattern is:

- strategy output is emitted too directly into UI tables;
- weak and strong candidates look similar;
- fallback/recovered values can pollute decision logic;
- ranking is not clearly separated from execution eligibility;
- UI filtering hides weak data instead of making decision quality better;
- post-run review is hard because candidate, decision, and outcome snapshots are not first-class artifacts.

V2 must fix the product brain, not merely reorganize screens.

---

## 3. Product Positioning

Opportunity Engine V2 is a real-time options decision cockpit for NIFTY, BANKNIFTY, SENSEX, and future stock-options workflows.

It should behave like:

- a candidate discovery system;
- a truth-first market-data validator;
- a scoring and ranking engine;
- an execution-safety gate;
- a capital-allocation guard;
- a replayable decision audit system;
- a dashboard cockpit for human review.

It should not behave like:

- a raw strategy-output table;
- a confidence-number generator;
- a fallback-data executor;
- a dashboard-only project;
- a black-box signal bot.

---

## 4. Non-Negotiable Product Principles

### 4.1 Data truth before trade intelligence

No ranking, execution gate, or UI label is allowed to treat fake, stale, fallback, or missing market data as equivalent to a fresh broker quote.

Required data states:

- `REALTIME`
- `DELAYED`
- `STALE`
- `FALLBACK`
- `MISSING`

Execution rule:

- `REALTIME` may become executable.
- `DELAYED`, `STALE`, and `FALLBACK` may be advisory only.
- `MISSING` must be blocked.

### 4.2 Candidates before trades

Strategies must produce candidates. They must not directly produce final executable trades.

A candidate is an observed market setup. A trade is only possible after data-quality validation, scoring, ranking, execution gating, and risk sizing.

### 4.3 Ranking is not execution

A high-ranked candidate can still be non-executable.

Examples:

- high score + wide spread = attractive but not executable;
- medium score + fresh quote + tight spread = potentially executable at smaller size.

### 4.4 Explain every decision

Every score, block, downgrade, and execution decision must have reason codes.

Required reason buckets:

- positive reasons;
- negative reasons;
- blocker reasons;
- downgrade reasons;
- execution reasons.

### 4.5 Human cockpit, not table viewer

The dashboard must expose decision state, not merely rows.

The top-level UI must distinguish:

- top opportunities;
- ready but not approved;
- watchlist / near executable;
- blocked candidates;
- data-quality health;
- regime state;
- risk state;
- decision timeline.

---

## 5. Target Architecture

```text
strategies / scanners / market observations
        ↓
candidate_pool
        ↓
data_quality_gate
        ↓
regime_detector
        ↓
scoring_engine
        ↓
ranking_engine
        ↓
lifecycle_engine
        ↓
execution_gate
        ↓
capital_allocator
        ↓
selector
        ↓
replay_store + dashboard cockpit
```

The V2 engine must run side-by-side with existing V1 paths until it proves better through tests, replay, and live/paper validation.

---

## 6. Required Modules

```text
core/opportunity/
    __init__.py
    candidate.py
    candidate_pool.py
    data_quality.py
    regime.py
    scoring.py
    ranking.py
    reason_codes.py
    lifecycle.py
    execution_gate.py
    capital_allocator.py
    replay_store.py
    outcome_tracker.py
    selector.py

dashboard/ui/
    opportunity_table.py
    decision_timeline.py
    data_quality_panel.py
    risk_panel.py
    regime_panel.py

tests/opportunity/
    test_candidate.py
    test_data_quality.py
    test_reason_codes.py
    test_scoring.py
    test_ranking.py
    test_lifecycle.py
    test_execution_gate.py
    test_capital_allocator.py
    test_replay_store.py
```

---

## 7. Candidate Contract

Every candidate must carry enough information to reconstruct why it existed and how it was judged.

Minimum fields:

```text
candidate_id
created_at
updated_at
symbol
underlying
option_type
strike
expiry
direction
source_strategy
setup_type
market_regime
data_quality_status
quote_source
underlying_ltp
option_ltp
bid
ask
spread
volume
open_interest
raw_features
score_components
final_score
rank
lifecycle_status
execution_status
position_size
positive_reasons
negative_reasons
blockers
decision_snapshot_id
```

A missing field must be explicit. Silent defaults are not allowed for decision-critical fields.

---

## 8. Lifecycle Model

Allowed lifecycle states:

```text
DISCOVERED
VALIDATING
WATCHLIST
READY
APPROVED
EXECUTED
REJECTED
EXPIRED
```

Lifecycle rules:

- A candidate starts as `DISCOVERED`.
- A candidate becomes `VALIDATING` only after minimum structural fields exist.
- A candidate becomes `WATCHLIST` when setup is interesting but not executable.
- A candidate becomes `READY` when score, data quality, and execution conditions are aligned.
- A candidate becomes `APPROVED` only after approval policy passes.
- A candidate becomes `EXECUTED` only after broker/execution confirmation.
- A candidate becomes `REJECTED` when hard blockers exist.
- A candidate becomes `EXPIRED` when its opportunity window is no longer valid.

---

## 9. Data-Quality Gate

The data-quality gate is a hard safety layer, not a scoring suggestion.

Hard blockers:

```text
MISSING_OPTION_LTP
MISSING_UNDERLYING_LTP
STALE_OPTION_LTP
STALE_UNDERLYING_LTP
FALLBACK_QUOTE
WIDE_SPREAD
INVALID_CONTRACT
ZERO_VOLUME_WHEN_VOLUME_REQUIRED
BROKER_FEED_DISCONNECTED
```

Rules:

- fallback-based candidates must not become executable;
- stale LTP must not become executable;
- invalid contract resolution must block execution;
- spread must be measured from bid/ask where available;
- derived or recovered quote values must be labeled as such.

---

## 10. Scoring Model

`confidence_raw` alone is not enough.

V2 scoring must be component-based:

```text
final_score =
    trend_score
  + momentum_score
  + volume_score
  + liquidity_score
  + regime_alignment_score
  + setup_quality_score
  - spread_penalty
  - stale_data_penalty
  - fallback_penalty
  - expiry_risk_penalty
  - volatility_noise_penalty
```

Each component must be inspectable and testable.

Score requirements:

- final score must be deterministic for the same input snapshot;
- each score component must have bounded ranges;
- score output must include reason codes;
- score alone must not grant execution permission.

---

## 11. Ranking Model

Ranking must compare all candidates, not merely display surviving rows.

Required ranking behavior:

- sort candidates by final score after hard-block handling;
- separate executable, watchlist, advisory, and blocked candidates;
- preserve blocked candidates for debugging;
- show rank movement over time where available;
- prevent fallback candidates from outranking real-quote executable candidates solely due to synthetic values.

---

## 12. Market Regime Model

The same candidate must be judged differently under different market regimes.

Required regimes:

```text
TRENDING_UP
TRENDING_DOWN
RANGE_BOUND
HIGH_VOLATILITY
LOW_VOLATILITY
EXPIRY_NOISE
OPENING_SPIKE
CLOSING_DECAY
UNKNOWN
```

Rules:

- unknown regime must reduce confidence, not inflate it;
- opening-spike setups must have shorter validity windows;
- expiry-noise regimes must increase risk penalties;
- range-bound regimes must penalize late breakout chasing.

---

## 13. Execution Gate

The execution gate decides whether a candidate may be traded now.

Execution statuses:

```text
EXECUTABLE
READY_NOT_APPROVED
WATCHLIST_ONLY
ADVISORY_ONLY
BLOCKED
```

Hard rule:

A candidate cannot be `EXECUTABLE` unless:

- data quality is `REALTIME`;
- contract is valid;
- option quote is fresh;
- spread is acceptable;
- risk limits allow it;
- lifecycle state is `READY` or stronger;
- blocker list is empty.

---

## 14. Capital Allocation

Execution without sizing is incomplete.

Required controls:

```text
risk_per_trade
max_daily_risk
max_open_positions
symbol_exposure_limit
strategy_exposure_limit
confidence_to_size_mapping
volatility_size_adjustment
spread_size_adjustment
loss_streak_throttle
```

Sizing output must include:

```text
allowed_lots
max_risk_amount
size_reason
size_blockers
```

No candidate may be labeled executable without a valid size decision.

---

## 15. Replay and Learning

Every candidate should be replayable.

Required snapshots:

```text
candidate_snapshot
data_quality_snapshot
score_snapshot
rank_snapshot
execution_gate_snapshot
risk_snapshot
entry_snapshot
exit_snapshot
outcome_snapshot
```

Replay must support:

- why a candidate was blocked;
- why a candidate was ranked highly;
- whether a rejected candidate later moved favorably;
- whether an executed candidate failed due to bad scoring, bad data, bad timing, or bad risk sizing.

---

## 16. Dashboard Cockpit Requirements

The V2 dashboard must be organized by decision usefulness.

Required panels:

1. Top Opportunities
2. Ready but Not Approved
3. Watchlist / Near Executable
4. Blocked Candidates
5. Data Quality Health
6. Regime Panel
7. Risk Panel
8. Decision Timeline
9. Replay / Outcome Review

Table rows must include:

```text
rank
symbol
contract
setup_type
final_score
execution_status
data_quality_status
spread
freshness_seconds
allowed_lots
primary_reason
primary_blocker
last_updated
```

---

## 17. MVP Scope

The first V2 MVP must not attempt everything.

MVP includes:

- candidate model;
- data-quality gate;
- reason codes;
- component scoring;
- ranking;
- lifecycle states;
- execution gate;
- capital-allocation shell;
- replay snapshot schema;
- focused unit tests;
- UI contract documentation.

MVP excludes:

- broker auto-execution changes;
- new strategy families;
- major dashboard redesign;
- machine-learning optimization;
- profitability claims;
- live-money automation changes.

---

## 18. PR Plan

### PR 1 — Product Bible

Scope:

- add this Product Bible;
- no runtime code;
- no behavior changes.

Acceptance:

- documentation renders cleanly;
- CI remains green;
- Portfolio CI remains green.

### PR 2 — Candidate + Reason-Code Contracts

Scope:

- add candidate dataclasses / typed contracts;
- add reason-code enums/constants;
- add tests.

Acceptance:

- deterministic candidate serialization;
- no hidden defaults for decision-critical fields;
- tests green.

### PR 3 — Data-Quality Gate

Scope:

- implement data-quality classification;
- enforce fallback/stale/missing execution blocks;
- add tests.

Acceptance:

- fallback cannot become executable;
- stale quotes cannot become executable;
- missing LTP is blocked.

### PR 4 — Scoring + Ranking

Scope:

- component score model;
- bounded score outputs;
- ranking buckets.

Acceptance:

- deterministic scores;
- blocked/advisory candidates preserved but separated;
- ranking tests green.

### PR 5 — Lifecycle + Execution Gate

Scope:

- lifecycle transitions;
- execution eligibility rules;
- blocker propagation.

Acceptance:

- invalid transitions fail;
- execution requires realtime data and no blockers;
- tests green.

### PR 6 — Capital Allocation Shell

Scope:

- position-size decision contract;
- risk limit checks;
- lot sizing outputs.

Acceptance:

- no executable candidate without sizing;
- risk-blocked candidates are not executable.

### PR 7 — Replay Store

Scope:

- snapshot schema;
- local replay artifact writer;
- outcome-ready schema.

Acceptance:

- every decision can be serialized;
- replay tests green.

### PR 8 — Dashboard Cockpit Integration

Scope:

- V2 panels behind feature flag;
- no removal of V1 UI until V2 is validated.

Acceptance:

- V1 dashboard still works;
- V2 cockpit displays ranked opportunities, watchlist, blocked candidates, and data-quality health.

---

## 19. Acceptance Gates

A V2 candidate can be considered production-safe only when:

- all candidate fields are explicit;
- fallback data never executes;
- stale quotes never execute;
- ranking separates executable, watchlist, advisory, and blocked candidates;
- execution status is explainable through reason codes;
- capital allocation produces a size or a block reason;
- replay snapshots exist for decisions;
- CI and Portfolio CI are green;
- live/paper validation confirms the decision stream behaves as expected.

---

## 20. Definition of Done

Opportunity Engine V2 is done only when Tradebot can show, for each trading session:

- what candidates were discovered;
- which were rejected and why;
- which were watchlisted and why;
- which became executable and why;
- what size was allowed;
- what changed over time;
- what happened after the decision;
- whether the decision logic should be improved.

If the system cannot explain these, it is not an opportunity engine. It is still a table viewer.

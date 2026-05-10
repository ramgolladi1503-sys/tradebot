# Aixion Tradebot — Elite Opportunity Engine Scope Bible

## Version

**Final Scope Bible v1.0**

## Repository

```text
ramgolladi1503-sys/tradebot
branch: feature/elite-opportunity-engine-bible
base: main
```

## Purpose

This document defines the final product scope, current-state assessment, architectural direction, implementation roadmap, acceptance gates, and elite-version requirements for the Tradebot Opportunity Engine.

The goal is not to build another signal spammer.

The goal is to build a disciplined, evidence-driven trading decision system that can answer:

```text
What is the best trade right now?
Why is it the best?
Is the data clean enough to trust?
Is it executable?
How much capital should be assigned?
What risk does it add?
What happened after the decision?
```

---

# 1. Executive Summary

The current Tradebot is no longer a basic bot. It already has serious building blocks:

- opportunity ranking
- trade scoring
- feature quality checks
- quote and liquidity validation
- review queue lifecycle
- candidate finalization assertions
- risk engine
- capital allocator
- threshold tuning
- learning hooks
- opportunity tests
- dashboard visibility

But it is not yet elite.

The main weakness is not lack of scoring or lack of modules.

The main weakness is this:

> The system does not yet have a strict, centralized, end-to-end data-truth and candidate-pool contract.

Because of that, fallback-derived values, display-only values, soft-recovered candidates, advisory candidates, and executable candidates can still become too close to each other in the pipeline.

A trading system can survive weak signals. It cannot survive lying data.

The elite version must enforce one hard rule:

```text
No candidate receives execution permission or capital unless its data lineage is clean.
```

---

# 2. Current Codebase Assessment

## 2.1 Current Strengths

### 2.1.1 Opportunity Engine Exists

The project already has `core/opportunity_engine.py`.

It connects confidence calibration, capital allocation, candidate finalization, contextual thresholds, decision authority, execution quality, feature quality, liquidity truth, learning state, portfolio optimization, risk engine, threshold audit, threshold tuning, and trade scoring.

This means the bot is already moving toward an opportunity engine. The issue is strictness and contract clarity.

### 2.1.2 Feature Quality Layer Exists

The project already has `core/feature_builder.py`.

It checks quote completeness, missing option LTP, missing bid/ask, missing spread, quote age, stale quote, quote consistency, bid/ask consistency, LTP vs book consistency, liquidity validation, spread quality, data confidence, and liquidity quality.

The elite version should promote this logic into a formal data-quality contract.

### 2.1.3 Trade Scoring Exists

The project already has `core/trade_scoring.py`.

It calculates final score using setup quality, confluence score, regime fit, liquidity quality, freshness quality, execution feasibility, data confidence, setup score, trigger score, entry quality score, family survival score, risk learning adjustment, fallback penalty, stale quote penalty, missing liquidity penalty, spread uncertainty penalty, and class caps.

The key problem is that fallback/degraded data should not merely be penalized. For execution-critical fields, fallback should be a hard execution blocker.

### 2.1.4 Review Queue Has Safety Logic

The project already has `core/review_queue.py`.

It handles advisory rows, execution entry lifecycle, display entry lifecycle, candidate identity, synthetic advisory protection, fallback execution source rejection, queue-only lifecycle protection, missing entry handling, and final emit enforcement.

Review queue should be the final enforcement wall, not the first place where truth is discovered.

### 2.1.5 Candidate Finalization Exists

The project already has `core/candidate_finalization.py`.

It asserts required fields for ranked and executable candidates. The elite version must extend these assertions to include data-quality and lineage fields.

### 2.1.6 Capital Allocator Exists

The project already has `core/capital_allocator.py`.

It supports allocation eligibility, selected-for-execution checks, max slots, per-symbol caps, per-theme caps, capital budget caps, replacement by better candidate, and allocation/deferred reasons.

The elite version must make it more data-quality-aware and portfolio-risk-aware.

### 2.1.7 Risk Engine Exists

The project already has `core/risk_engine.py`.

It evaluates stop distance, risk-reward ratio, position size estimate, portfolio heat, directional heat, family exposure, correlation penalty, exposure blockers, daily kill switch, regime failure throttles, family failure throttles, and offline risk learning adjustment.

The next upgrade is to treat bad data as a risk condition, not only price/stop/portfolio exposure.

### 2.1.8 Opportunity Tests Exist

The project already has `tests/test_opportunity_engine.py`.

It tests timing score contribution, executable candidate ranking, display-only candidate not being selected, executable/advisory separation, liquidity gradients, spread penalties, deterministic ranking, and top-opportunity selection.

The missing tests are hard anti-lie tests around fallback-derived execution fields and degraded data lineage.

---

# 3. Current Core Problem

## 3.1 The Bot Has Intelligence Pieces, But Not a Strong Enough Truth Contract

The current system contains many intelligent components, but the pipeline still needs a centralized truth layer that separates:

```text
visible candidate
interesting candidate
rankable candidate
advisory candidate
near-executable candidate
executable candidate
capital-worthy candidate
```

These are not the same thing.

A candidate can be shown on the dashboard without being tradable. A candidate can have a high advisory score without being executable. A candidate can be executable without deserving capital. A candidate can be attractive but blocked due to portfolio risk.

## 3.2 The Most Dangerous Area: Fallback Promotion

The code contains fallback support in `core/engine_phase2_adapter.py`.

Fallbacks can fill missing values such as:

- `quote_age_sec`
- `spread_pct`
- `liquidity_score`
- `quote_source`
- `depth_score`
- `tick_volume`

This is acceptable for display continuity and diagnostics. It is not acceptable for execution truth.

Hard rule:

```text
Fallback data can support display.
Fallback data cannot support execution.
```

Example 1: If `spread_pct` is defaulted because bid/ask is missing, the candidate may be shown as advisory. It must not be selected for execution.

Example 2: If `liquidity_score` is defaulted because no live book exists, the candidate may remain in debug or advisory. It must receive zero capital.

---

# 4. Final Product Vision

The elite version of Tradebot should behave like a disciplined trading desk assistant.

It should:

1. collect candidates from multiple strategies
2. validate the data behind each candidate
3. stamp data lineage on every execution-critical field
4. separate advisory candidates from executable candidates
5. score candidates with explainable components
6. rank opportunities globally
7. evaluate risk and portfolio impact
8. allocate capital only to clean candidates
9. track trade lifecycle after selection
10. learn from outcomes and near-misses

It should not behave like:

```text
strategy → emit rows → dashboard filter → manual guessing
```

It should behave like:

```text
strategy candidates → data truth → scoring → ranking → risk → allocation → execution decision → lifecycle learning
```

---

# 5. Non-Negotiable Design Principles

## Principle 1 — Data Truth Before Score

Bad order:

```text
score → rank → maybe check data
```

Correct order:

```text
data truth → candidate class → score → rank → risk → allocation
```

## Principle 2 — Display Is Not Execution

A candidate can be visible and still non-executable.

Example:

```text
High momentum + missing bid/ask = advisory only
```

## Principle 3 — Fallback Is Never Execution-Grade

Any fallback-derived execution-critical field must block execution.

Execution-critical fields include option LTP, bid, ask, spread, liquidity score, instrument token, contract mapping, execution entry, and quote age.

## Principle 4 — High Score Cannot Override Dirty Data

Correct behavior:

```text
final_score = high advisory value
execution_allowed = false
capital_assigned = 0
```

## Principle 5 — Capital Allocation Requires Clean Truth

Capital should only go to candidates that pass data truth, execution truth, scoring threshold, risk budget, portfolio exposure limits, and lifecycle readiness.

---

# 6. Target Architecture

```text
Market Feed / Broker Quote
        ↓
Quote Truth + Data Lineage Layer
        ↓
Feature Builder
        ↓
Strategy Candidate Generation
        ↓
Canonical Candidate Pool
        ↓
Opportunity Engine
        ↓
Trade Scoring Engine
        ↓
Risk Engine
        ↓
Capital Allocator
        ↓
Final Execution Gate
        ↓
Review Queue / Approval / Execution
        ↓
Lifecycle + Outcome Logging
        ↓
Learning / Calibration / Threshold Tuning
        ↓
Dashboard Decision Console
```

---

# 7. Required Core Build Scope

## 7.1 Create `core/data_quality.py`

Purpose: create one official module responsible for data truth, data lineage, and execution-critical data validation.

Responsibilities:

- detect stale quotes
- detect missing LTP
- detect missing bid/ask
- detect missing spread
- detect fallback spread
- detect fallback liquidity
- detect unknown quote source
- detect synthetic/offhours data
- detect recovered execution entry
- detect contract fallback
- assign data quality grade
- emit execution truth blockers

Output contract:

```python
{
    "data_quality_grade": "A",
    "execution_truth_allowed": True,
    "execution_truth_blockers": [],
    "fallback_fields": [],
    "lineage": {
        "ltp": "LIVE_BROKER",
        "bid": "LIVE_BOOK",
        "ask": "LIVE_BOOK",
        "spread": "LIVE_BOOK",
        "liquidity": "DERIVED_FROM_BOOK",
        "contract": "EXACT_MATCH",
        "execution_entry": "ASK"
    }
}
```

Grade definitions:

```text
A = live, complete, fresh, broker/book-confirmed, executable-grade
B = mostly live, minor weakness, executable only if no hard blocker
C = partial or degraded, advisory/near-executable only
D = fallback/recovered/unknown, never executable
F = invalid, reject/debug only
```

Acceptance criteria:

- fallback fields are always visible
- unknown quote source is never execution-grade
- stale quote is never execution-grade
- missing bid/ask is never execution-grade
- fallback spread is never execution-grade
- fallback liquidity is never execution-grade

## 7.2 Create `core/candidate_pool.py`

Purpose: create a formal pool where raw strategy outputs become normalized, truth-stamped candidates before ranking.

Responsibilities:

- accept raw candidates from strategy modules
- normalize candidate schema
- attach data-quality contract
- preserve rejected candidates
- preserve advisory candidates
- preserve near-executable candidates
- pass valid candidates to opportunity engine
- maintain candidate lifecycle stage

Candidate lifecycle states:

```text
RAW
NORMALIZED
DATA_INVALID
ADVISORY_ONLY
NEAR_EXECUTABLE
EXECUTABLE
SELECTED
REJECTED
```

Candidate pool outputs:

```text
top_executable_candidates
near_executable_candidates
advisory_candidates
rejected_candidates
debug_candidates
```

## 7.3 Harden `core/engine_phase2_adapter.py`

Whenever fallback is used, stamp explicit lineage.

Example:

```python
candidate["spread_lineage"] = "FALLBACK_DEFAULT"
candidate["fallback_fields"].append("spread_pct")
candidate["execution_truth_allowed"] = False
candidate["execution_truth_blockers"].append("fallback_spread")
```

Required fallback blockers:

```text
fallback_spread
fallback_liquidity
fallback_quote_age
unknown_quote_source
synthetic_depth_score
synthetic_tick_volume
```

## 7.4 Harden `core/trade_scoring.py`

Separate score from execution eligibility.

```text
score = ranking usefulness
execution_truth_allowed = tradability truth
```

A candidate may have a useful advisory score and still be non-executable.

## 7.5 Harden `core/opportunity_engine.py`

Candidate class derivation must depend on data truth first.

Mandatory rule:

```text
if execution_truth_allowed is false:
    candidate_class cannot be EXECUTABLE
    selected_for_execution must be false
    capital_assigned must be 0
```

## 7.6 Harden `core/review_queue.py`

Before any `EXECUTE` final action:

```text
execution_truth_allowed == true
data_quality_grade in A/B
execution_entry_source not in recovered_fallback/rest_fallback/synthetic_offhours
fallback_fields contains no execution-critical field
```

## 7.7 Harden `core/candidate_finalization.py`

Additional executable fields:

```text
data_quality_grade
execution_truth_allowed
execution_truth_blockers
price_lineage
spread_lineage
liquidity_lineage
contract_lineage
fallback_fields
```

## 7.8 Upgrade `core/capital_allocator.py`

Required upgrades:

- consume `data_quality_grade`
- consume `execution_truth_allowed`
- assign zero capital to dirty candidates
- penalize same-symbol clustering
- penalize same-direction clustering
- calculate quantity from risk budget
- expose allocation blockers
- expose portfolio impact

Required output:

```text
capital_assigned
qty_recommended
risk_amount
risk_percent
allocation_reason
allocation_blockers
portfolio_impact
size_multiplier_effective
```

## 7.9 Upgrade `core/risk_engine.py`

Bad data must be treated as a risk blocker.

New risk blockers:

```text
low_data_quality
fallback_execution_field
unknown_quote_source
stale_execution_quote
spread_unverified
missing_bid_ask
contract_fallback_not_execution_safe
```

---

# 8. Dashboard Scope

The dashboard must become a decision console.

## 8.1 System Truth Bar

Shows market mode, broker connection, feed freshness, depth websocket status, quote health, fallback count, unknown quote source count, executable count, near-executable count, advisory count, rejected count, kill switch status, daily risk used, and open risk.

## 8.2 Top Executable Opportunities

Only candidates that pass execution truth.

Columns:

```text
Rank
Symbol
CE/PE
Strike
Expiry
Final Score
Data Grade
Entry
Stop
Target
Qty
Risk
Capital Assigned
Why Ranked
Why Executable
```

Hard rule:

```text
No fallback-derived execution candidate appears here.
```

## 8.3 Near Executable

Candidates that are close but blocked.

Possible blockers:

```text
spread_slightly_wide
quote_age_near_limit
liquidity_below_threshold
waiting_for_bid_ask
risk_budget_pending
```

## 8.4 Advisory Only

Candidates useful for market context but not tradable.

Examples:

```text
fallback_spread
fallback_liquidity
unknown_quote_source
synthetic_offhours
missing_bid_ask
recovered_contract
```

## 8.5 Rejected / Debug Candidates

Must include reject reason, stage rejected, primary blocker, data grade, fallback fields, and source strategy.

## 8.6 Data Quality Board

Shows fallback fields by candidate, quote age distribution, unknown quote source count, missing bid/ask count, spread fallback count, liquidity fallback count, stale quote count, and data grade distribution.

## 8.7 Score Breakdown Panel

For each candidate:

```text
setup_score
trigger_score
entry_quality_score
liquidity_score
freshness_score
execution_score
risk_score
data_confidence
penalty_total
class_cap
final_score
rank_reason
primary_blocker
```

---

# 9. Testing Scope

Required new tests:

1. fallback spread blocks execution
2. fallback liquidity blocks execution
3. recovered fallback entry blocks execution
4. unknown quote source blocks execution
5. stale quote blocks execution before scoring
6. display entry cannot become execution entry
7. high score cannot override data truth
8. allocation respects data truth
9. advisory can rank high but not execute
10. candidate finalization rejects dirty executable

---

# 10. Acceptance Gates

## Gate 1 — Data Truth Gate

- every candidate has `data_quality_grade`
- every candidate has field lineage
- fallback fields are visible
- fallback execution fields are hard blockers
- unknown quote source is not executable
- stale quote is not executable
- missing bid/ask is not executable

## Gate 2 — Candidate Pool Gate

- raw candidates enter canonical candidate pool
- rejected candidates are preserved
- advisory candidates are preserved
- near-executable candidates are preserved
- executable candidates are separated cleanly
- dashboard consumes pool outputs

## Gate 3 — Ranking Gate

- score distribution is meaningful
- score breakdown is visible
- advisory candidates do not pollute executable list
- high score cannot override dirty data
- ranking is deterministic for identical inputs

## Gate 4 — Allocation Gate

- capital assigned only to clean executable candidates
- dirty candidates get zero capital
- duplicate exposure is penalized
- per-symbol caps are enforced
- per-theme caps are enforced
- allocation reason is visible

## Gate 5 — Risk Gate

- risk engine blocks bad data
- risk engine blocks bad RR
- risk engine blocks portfolio heat breaches
- risk engine blocks daily kill switch
- risk engine explains reason codes

## Gate 6 — Dashboard Gate

- top executable section exists
- near-executable section exists
- advisory section exists
- rejected/debug section exists
- data quality board exists
- score breakdown exists
- user can see why a trade is or is not executable

## Gate 7 — Regression Gate

These must never return:

```text
fallback candidate selected for execution
display-only candidate selected for execution
stale quote executable
unknown quote source executable
missing bid/ask executable
recovered fallback entry executable
dashboard row without blocker reason
capital assigned to advisory candidate
```

---

# 11. Implementation Roadmap

## Phase 1 — Data Truth Hardening

Goal: make fallback or degraded data impossible to execute.

Work:

- create `core/data_quality.py`
- stamp lineage in `engine_phase2_adapter.py`
- block fallback execution in opportunity engine
- add tests for fallback execution truth

Commit:

```text
feat: add data truth contract and block fallback-derived execution
```

## Phase 2 — Candidate Pool Contract

Goal: make candidate lifecycle explicit before ranking.

Work:

- create `core/candidate_pool.py`
- normalize strategy outputs
- preserve rejected/advisory/near-executable candidates
- emit clean candidate collections

Commit:

```text
feat: introduce canonical candidate pool and lifecycle statuses
```

## Phase 3 — Opportunity Engine Hardening

Goal: make ranking obey data truth.

Work:

- modify candidate class derivation
- enforce execution truth before selection
- separate advisory ranking from executable ranking
- improve score explanations

Commit:

```text
fix: enforce data truth before opportunity selection
```

## Phase 4 — Capital and Risk Integration

Goal: make allocation risk-aware and data-aware.

Work:

- consume data quality in risk engine
- consume data quality in capital allocator
- produce allocation explanation
- block allocation for degraded candidates

Commit:

```text
feat: make capital allocation data-quality and risk aware
```

## Phase 5 — Dashboard Decision Console

Goal: make UI explain decisions instead of just showing rows.

Work:

- add top executable opportunities
- add near-executable board
- add advisory board
- add rejected/debug board
- add data quality board
- add score breakdown panel

Commit:

```text
feat: upgrade dashboard into ranked opportunity decision console
```

## Phase 6 — Outcome Learning

Goal: make the system learn from decisions.

Work:

- log candidate ID through lifecycle
- log selected vs rejected outcomes
- track MFE/MAE
- track slippage
- track fallback false positives
- generate score-band calibration reports

Commit:

```text
feat: add opportunity outcome learning and score calibration reports
```

---

# 12. File-Level Work Plan

## Create

```text
core/data_quality.py
core/candidate_pool.py
tests/test_data_quality.py
tests/test_candidate_pool.py
tests/test_fallback_execution_truth.py
docs/ELITE_OPPORTUNITY_ENGINE_BIBLE.md
```

## Modify

```text
core/engine_phase2_adapter.py
core/opportunity_engine.py
core/trade_scoring.py
core/review_queue.py
core/candidate_finalization.py
core/capital_allocator.py
core/risk_engine.py
dashboard/streamlit_app_runtime.py
tests/test_opportunity_engine.py
```

## Optional Later

```text
core/opportunity_outcomes.py
core/score_calibration.py
core/portfolio_exposure_graph.py
core/regime_playbook_router.py
```

---

# 13. Immediate Branch Plan

Current work branch:

```text
feature/elite-opportunity-engine-bible
```

No direct commits to `main`.

No merge into `main` until:

- tests pass
- dashboard validates
- 9:30 AM market validation is successful
- fallback/data-truth gates are clean
- user approves merge

---

# 14. Definition of Done

The elite Opportunity Engine is done when every candidate can answer these ten questions:

1. Why does this candidate exist?
2. Which strategy produced it?
3. What exact data supports it?
4. Which fields are live, derived, fallback, recovered, synthetic, or unknown?
5. Why is it ranked where it is?
6. Why is it executable or not executable?
7. How much capital should it receive?
8. What risk does it add to the portfolio?
9. What happened after the decision?
10. Should this strategy/setup be trusted more or less next time?

If the bot cannot answer these, it is not elite.

---

# 15. Final No-BS Assessment

The project already has serious foundations:

```text
opportunity engine
feature quality
trade scoring
risk engine
capital allocator
review queue
candidate finalization
opportunity tests
```

This is not a toy system anymore.

The weak point is strict truth enforcement.

Fallback, recovered, synthetic, display-only, and unknown-source data must never be allowed to behave like clean execution data.

Do not add more strategies yet.

Do not add stock options yet.

Do not polish UI first.

Do this first:

```text
Make the bot brutally honest.
```

Then make it more powerful.

The elite version is not the bot that shows the most trades.

The elite version is the bot that rejects bad trades faster than a human, ranks clean opportunities better than a dashboard, and protects capital when the data is not good enough.

That is the real edge.

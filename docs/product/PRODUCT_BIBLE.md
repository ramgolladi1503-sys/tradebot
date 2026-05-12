# PRODUCT_BIBLE.md

# Aixion Quant Console / Tradebot Product Bible

**Product:** Aixion Quant Console / Tradebot  
**Document owner:** Ram  
**Status:** Living source of truth  
**Last updated:** 2026-05-12  

---

## 1. Product identity

Aixion Quant Console / Tradebot is a production-style options trading decision system focused on **market-data validation, opportunity ranking, execution readiness, risk control, observability, and operator confidence**.

It is not just a script that prints trades.

It must behave like a disciplined trading operations console:

```text
market state -> candidate pool -> quality scoring -> ranking -> execution gates -> risk sizing -> review/execution -> audit trail
```

The current system has strong infrastructure, logs, CI, dashboarding, contract-resolution work, and runtime-health thinking. The missing edge is the intelligence layer: ranked opportunity selection with honest data-quality handling.

---

## 2. Brutal product truth

The current UI evidence shows a dangerous weakness: rows are visible, but that does not mean opportunities are high quality.

Known current product weaknesses:

1. Many opportunities look too similar.
2. Confidence values are narrow and weakly separated.
3. `recovered_fallback` appears too often.
4. Fallback data can make the UI look useful while hiding poor data quality.
5. The system behaves like a filtered output viewer, not a true opportunity engine.
6. BUY-side bias appears too strong.
7. Capital allocation is not yet a first-class product behavior.
8. Ranking is not yet strong enough to justify trust.

Hard rule:

> A system that cannot explain why trade A is materially better than trade B is not an opportunity engine. It is a table printer.

---

## 3. Product mission

Build a trading decision console that helps the operator answer:

1. What are the best opportunities right now?
2. Why are they better than the rest?
3. Can they be executed safely?
4. What data quality supports or blocks them?
5. What risk should be assigned?
6. What changed since the last cycle?
7. What should be ignored, queued, watched, or executed?

---

## 4. Non-negotiable product principles

### 4.1 Truth over activity

The product must prefer showing fewer honest opportunities over many weak rows.

Bad:

```text
20 rows shown, unclear edge, fallback-heavy, all BUY
```

Good:

```text
3 top-ranked opportunities, clear scores, clean quotes, executable status, blocker explanations
```

### 4.2 Fallback is not execution truth

Fallback data is useful for continuity and advisory awareness. It is not good enough for execution.

Rule:

```text
fallback-derived quote -> advisory/watchlist only
fallback-derived executable trade -> forbidden unless explicitly whitelisted by a documented safety gate
```

### 4.3 Ranking must create separation

A ranking engine must produce meaningful differences.

Weak ranking:

```text
0.46, 0.45, 0.44, 0.43
```

Useful ranking:

```text
0.86 strong
0.71 good
0.54 watch
0.22 ignore
```

### 4.4 Candidate lifecycle must be explicit

Every opportunity must have a clear lifecycle state:

```text
RAW_CANDIDATE
SCORED_CANDIDATE
RANKED_CANDIDATE
EXECUTABLE
READY_NOT_APPROVED
QUEUE_ONLY
ADVISORY_ONLY
BLOCKED
EXPIRED
```

No row should appear without lifecycle context.

### 4.5 UI must not invent truth

The dashboard must read product truth from engine artifacts. It must not recompute important trading decisions in a way that disagrees with runtime logs.

### 4.6 Risk is part of the product, not a later add-on

An opportunity without risk sizing is incomplete.

Every top opportunity eventually needs:

```text
score
rank
confidence
regime
data_quality
liquidity
spread
stop
target
position_size
max_loss
primary_blocker
```

---

## 5. Target user

### 5.1 Primary user

The primary user is the builder/operator: Ram.

Needs:

- See high-quality trades fast.
- Debug why trades are blocked.
- Know whether feed is reliable.
- Know whether broker/contract mapping is valid.
- Avoid trusting fake/fallback data.
- Use the project as portfolio evidence for QA/SDET + fintech reliability.

### 5.2 Secondary user

A reviewer, recruiter, consultant, or technical interviewer.

Needs:

- Understand architecture.
- See acceptance gates.
- See failure handling.
- See release discipline.
- See project maturity beyond toy trading scripts.

---

## 6. Product positioning

Aixion Quant Console is positioned as:

> A real-time options decision and reliability console that converts noisy strategy output into ranked, auditable, risk-aware opportunities.

It is not positioned as:

- A guaranteed profit bot.
- A black-box magic trading model.
- A simple Streamlit dashboard.
- A broker wrapper.
- A backtest-only toy.

---

## 7. Core product modules

### 7.1 Market data layer

Responsibilities:

- Broker feed integration.
- Option quote freshness.
- LTP validation.
- Spread/depth checks.
- Feed runtime state.
- Stale-feed detection.
- Snapshot persistence.

Must expose:

```text
feed_status
quote_age_ms
ltp_source
spread
bid
ask
depth_available
is_stale
stale_reason
fallback_used
```

### 7.2 Candidate pool

Responsibilities:

- Collect all strategy-generated opportunities.
- Preserve strategy source.
- Preserve raw reasons.
- Prevent early UI emission.
- Normalize all candidates into a common schema.

Required fields:

```text
candidate_id
symbol
instrument
option_type
strike
expiry
strategy_family
direction
raw_signal_strength
raw_confidence
source_strategy
created_at
```

### 7.3 Data-quality gate

Responsibilities:

- Reject or demote candidates based on data quality.
- Prevent fallback-driven execution.
- Mark stale quote issues clearly.

Output:

```text
data_quality_score
data_quality_status
fallback_used
quote_valid
spread_valid
depth_valid
primary_data_blocker
```

### 7.4 Scoring engine

Responsibilities:

- Convert raw candidates into comparable opportunity scores.
- Produce meaningful separation.
- Use multiple factors.

Scoring factors:

```text
momentum_score
volatility_expansion_score
volume_score
liquidity_score
spread_score
regime_fit_score
theta_risk_score
time_to_expiry_score
data_quality_score
strategy_edge_score
```

Target formula concept:

```text
opportunity_score = edge_score * probability_weight * liquidity_weight * data_quality_weight * regime_weight
```

### 7.5 Ranking engine

Responsibilities:

- Sort candidates by final score.
- Segment into top opportunities, watchlist, advisory, blocked.
- Avoid showing duplicate correlated trades as independent top picks.

Must support:

```text
top_n_by_symbol
top_n_global
rank_delta
score_delta
candidate_cluster
correlation_group
```

### 7.6 Regime detector

Responsibilities:

- Identify market behavior.
- Adjust scoring weights.
- Avoid bullish-only logic.

Regimes:

```text
TRENDING_UP
TRENDING_DOWN
RANGE_BOUND
HIGH_VOLATILITY
LOW_VOLATILITY
EXPIRY_COMPRESSION
NEWS_SPIKE
UNKNOWN
```

### 7.7 Execution gate

Responsibilities:

- Decide whether candidate can be executed, queued, watched, or blocked.
- Enforce hard safety rules.

Must never allow:

```text
fallback quote -> executable
stale option LTP -> executable
missing contract token -> executable
spread too wide -> executable
risk halt active -> executable
```

### 7.8 Risk and allocation layer

Responsibilities:

- Assign risk budget.
- Limit exposure.
- Prevent overconcentration.
- Size positions based on quality and market conditions.

Required output:

```text
risk_bucket
position_size
max_loss
stop_loss
target
risk_reward
capital_allocation_pct
```

### 7.9 Dashboard/UI

Responsibilities:

- Show ranked top opportunities first.
- Show candidate diagnostics second.
- Make blockers visible.
- Avoid hiding weak data behind filters.

Required dashboard sections:

```text
Top Opportunities
Executable Now
Near Executable / Watchlist
Advisory Only
Blocked Candidates
Feed Health
Risk State
Decision Audit
```

### 7.10 Audit and reporting

Responsibilities:

- Persist decisions.
- Explain lifecycle transitions.
- Support release validation.
- Support post-market analysis.

Artifacts:

```text
runtime events
trade logs
ranking snapshots
feed health snapshots
execution intents
reconciliation output
failure reports
release validation report
```

---

## 8. Product invariants

These must always hold.

### Invariant 1: Fallback cannot be executable

```text
fallback_used == true -> execution_status != EXECUTABLE
```

### Invariant 2: Stale quote cannot be executable

```text
quote_valid == false -> execution_status != EXECUTABLE
```

### Invariant 3: Missing contract cannot be executable

```text
contract_token is null -> execution_status != EXECUTABLE
```

### Invariant 4: Risk halt blocks execution

```text
risk_halt_active == true -> execution_allowed == false
```

### Invariant 5: UI row must have explanation

Every visible row must include:

```text
score
rank
candidate_status
execution_status
primary_reason
primary_blocker
```

### Invariant 6: Top opportunity must be materially better

Top-ranked opportunities must show meaningful score separation or explain why scores are compressed.

### Invariant 7: BUY-only output is suspicious

If output is mostly one-directional, system must expose directional-bias diagnostics.

---

## 9. MVP success definition

The MVP is successful when the product can:

1. Generate a candidate pool.
2. Score candidates using data quality, liquidity, regime, and strategy edge.
3. Rank top opportunities with meaningful separation.
4. Demote fallback/stale candidates to advisory or blocked.
5. Show executable, watchlist, advisory, and blocked sections clearly.
6. Persist ranking and decision evidence.
7. Pass CI and release validation.
8. Explain why no good trade exists.

The MVP is not successful if:

- The UI only lists emitted rows.
- Fallback candidates appear executable.
- Everything has similar confidence.
- BUY-only spam remains unexplained.
- Top opportunities are not clearly better.
- There is no risk sizing or blocker transparency.

---

## 10. Elite version success definition

The elite version is successful when the product behaves like a professional trading operations system:

1. Real-time feed health is continuously monitored.
2. Candidate pool is broad and multi-strategy.
3. Ranking adapts to market regime.
4. Top opportunities are clearly separated.
5. Execution gates are strict and auditable.
6. Risk allocation is automatic and conservative.
7. Backtest/paper/live behavior is comparable.
8. Failure modes are documented and tested.
9. Dashboard explains decision truth without recomputation drift.
10. Release validation prevents unsafe changes.
11. Agents can work safely using documented guardrails.
12. Every project claim can be backed by logs, tests, screenshots, and docs.

---

## 11. Current product priorities

### Priority 1: Candidate pool abstraction

Stop emitting strategy rows directly to the UI.

Build:

```text
strategies -> candidate_pool -> scoring -> ranking -> gates -> UI
```

### Priority 2: Fallback demotion

Patch rule:

```text
fallback_used == true -> ADVISORY_ONLY or BLOCKED
```

### Priority 3: Real score separation

Improve score model so top opportunities are materially different from weak ones.

### Priority 4: Top opportunities UI

Dashboard must show ranked opportunity sections before debug tables.

### Priority 5: Directional-bias diagnostics

If all rows are BUY, the system must explain whether the market is actually bullish or the strategy is biased.

### Priority 6: Capital allocation

Add position size and risk budget after ranking is trustworthy.

---

## 12. Product anti-goals

Do not build:

- Cosmetic dashboard changes that hide weak ranking.
- More filters instead of better scoring.
- Execution paths that tolerate stale/fallback quote truth.
- Silent fallback behavior.
- ML complexity before deterministic scoring is honest.
- Live execution before paper validation is stable.
- A dashboard that looks impressive but cannot explain blockers.

---

## 13. Product vocabulary

| Term | Meaning |
|---|---|
| Candidate | A raw or normalized possible trade idea. |
| Opportunity | A candidate that passed scoring and ranking quality checks. |
| Executable | Safe to execute now, subject to approval/risk. |
| Queue-only | Interesting but not ready for execution. |
| Advisory-only | Useful information, not tradable. |
| Blocked | Candidate rejected by hard gate. |
| Fallback | Recovered or estimated data used when direct data was missing. |
| Data quality | Trust level of quote/feed/contract/liquidity data. |
| Regime | Current market behavior context. |
| Score separation | Difference between top candidate and lower candidates. |
| Execution truth | Final source of whether the trade is actually allowed. |

---

## 14. Product north star

The product north star is not number of rows.

The north star is:

```text
high-confidence ranked opportunities with honest execution readiness and measurable risk
```

If the system shows fewer trades but each one is explainable, ranked, data-clean, and risk-aware, the product is improving.

If it shows more trades but they are fallback-heavy, score-compressed, and visually similar, the product is lying.

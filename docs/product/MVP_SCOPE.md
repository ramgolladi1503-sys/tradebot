# MVP_SCOPE.md

# Aixion Quant Console / Tradebot MVP Scope

**Status:** Living MVP contract  
**Owner:** Ram  
**Last updated:** 2026-05-12

---

## 1. MVP objective

The MVP must turn Tradebot from a filtered trade-row viewer into a ranked opportunity engine.

The MVP is not complete just because rows appear in the dashboard. Rows are cheap. Ranking, execution truth, data-quality discipline, and blocker clarity are the product.

Target flow:

```text
strategy signals -> candidate pool -> data-quality gate -> scoring -> ranking -> execution gate -> risk summary -> dashboard/audit
```

---

## 2. MVP problem statement

Current product risk:

- Many candidates look similar.
- Confidence values do not create enough separation.
- Fallback/recovered data appears too often.
- BUY-side output may be biased.
- UI filters hide weak rows instead of improving decision quality.
- Capital allocation and risk sizing are not yet first-class output.

The MVP must fix the decision layer before adding fancy visuals.

---

## 3. MVP must-have modules

### 3.1 Candidate pool

Build a normalized candidate pool before dashboard emission.

Required fields:

```text
candidate_id
created_at
symbol
instrument
option_type
strike
expiry
direction
strategy_family
source_strategy
raw_confidence
raw_reason
```

Acceptance:

- Every strategy writes into the pool.
- UI no longer depends only on raw emitted rows.
- Candidate lifecycle state is persisted.

### 3.2 Data-quality gate

The gate must classify quote/feed/contract trust.

Required fields:

```text
quote_valid
quote_age_ms
fallback_used
ltp_source
spread_valid
depth_valid
contract_valid
data_quality_status
primary_data_blocker
```

Mandatory rule:

```text
fallback_used == true -> not executable
```

### 3.3 Scoring engine

The engine must produce a final opportunity score with meaningful separation.

Minimum score components:

```text
strategy_edge_score
momentum_score
liquidity_score
spread_score
volatility_score
regime_fit_score
data_quality_score
time_decay_risk_score
```

Acceptance:

- Top opportunity is visibly better than weak candidates.
- Score compression is flagged.
- Score explanation is available per candidate.

### 3.4 Ranking engine

The engine must rank across all valid candidates.

Required outputs:

```text
rank
rank_bucket
score_delta_from_top
candidate_cluster
is_top_opportunity
```

Buckets:

```text
TOP_OPPORTUNITY
EXECUTABLE_NOW
WATCHLIST
ADVISORY_ONLY
BLOCKED
```

### 3.5 Execution gate

Hard blockers:

```text
stale_feed
stale_option_ltp
fallback_quote
missing_contract
wide_spread
risk_halt
missing_stop_or_target
```

Output:

```text
execution_allowed
execution_status
primary_blocker
blocker_details
```

### 3.6 Risk summary

MVP-level risk does not need advanced portfolio optimization, but every executable candidate must show:

```text
suggested_position_size
max_loss
stop_loss
target
risk_reward
capital_allocation_pct
```

### 3.7 Dashboard sections

Minimum UI sections:

1. Feed and risk health.
2. Top opportunities.
3. Executable now.
4. Watchlist / near executable.
5. Advisory only.
6. Blocked candidates.
7. Debug candidate table.

The debug table must not be the main product.

---

## 4. Out of scope for MVP

Do not include in MVP:

- Live auto-execution without approval.
- Complex ML ranking before deterministic scoring is stable.
- Options portfolio Greeks engine.
- Multi-broker routing.
- Fully autonomous capital allocation.
- Social/mobile notifications beyond basic alerts.
- Cosmetic UI redesign without ranking fixes.

---

## 5. MVP success criteria

The MVP passes only if:

- Fallback candidates are never executable.
- Stale quote candidates are never executable.
- Missing contract candidates are never executable.
- Top opportunities show score separation.
- BUY-only output is diagnosed.
- Dashboard explains why each candidate is executable, queued, advisory, or blocked.
- CI and health gates pass.
- Release validation checklist is completed.

---

## 6. MVP failure criteria

The MVP fails if:

- UI still only shows emitted rows.
- `recovered_fallback` appears in executable trades.
- Confidence remains tightly compressed without warning.
- Filters are used as a substitute for ranking.
- Dashboard hides blockers.
- There is no persisted decision evidence.
- Risk sizing is absent for executable trades.

---

## 7. Required MVP tests

Minimum test groups:

```bash
pytest -q tests/test_candidate_pool.py
pytest -q tests/test_data_quality_gate.py
pytest -q tests/test_opportunity_scoring.py
pytest -q tests/test_ranking_engine.py
pytest -q tests/test_execution_gate.py
pytest -q tests/test_dashboard_table_model.py
pytest -q tests/test_release_validation.py
```

If exact files do not exist yet, create equivalent tests near the relevant modules.

---

## 8. MVP demo script

Demo must show:

1. Feed health status.
2. Candidate pool count.
3. Top ranked opportunities.
4. One executable example with clean data.
5. One fallback candidate demoted to advisory.
6. One stale candidate blocked.
7. One no-trade scenario where the system honestly says no good trade exists.

---

## 9. MVP implementation order

1. Add candidate schema.
2. Route strategies into candidate pool.
3. Add data-quality gate.
4. Add fallback demotion invariant.
5. Add scoring components.
6. Add ranking buckets.
7. Add dashboard sections.
8. Add persistence/audit fields.
9. Add tests.
10. Run release validation.

---

## 10. MVP definition of done

MVP is done when a reviewer can open the dashboard and immediately understand:

```text
what is best
why it is best
whether it is executable
what blocks the rest
what risk is attached
whether the data is trustworthy
```

Anything less is not an MVP. It is still infrastructure.

# ROADMAP.md

# Aixion Quant Console / Tradebot Roadmap

**Purpose:** Move from infrastructure-heavy trade rows to elite ranked opportunities.

---

## Phase 0: Stabilize truth

Goal: stop the system from lying to itself.

Deliverables:

- Fallback demotion rule.
- Stale quote execution block.
- Missing contract execution block.
- Dashboard blocker visibility.
- Feed-health single-source rule.

Exit criteria:

- No fallback candidate is executable.
- No stale candidate is executable.
- Dashboard shows blocker reason for every blocked row.

---

## Phase 1: Candidate pool MVP

Goal: separate raw strategies from product-facing opportunities.

Deliverables:

- Candidate schema.
- Candidate pool collector.
- Candidate lifecycle states.
- Candidate snapshot persistence.
- Candidate-pool tests.

Exit criteria:

- Strategies no longer directly define final UI truth.
- Each candidate has source strategy and lifecycle.

---

## Phase 2: Data-quality gate

Goal: make quote/feed/contract quality explicit.

Deliverables:

- Quote freshness scoring.
- Fallback marker.
- Spread/depth validation.
- Contract-valid marker.
- Primary data blocker.

Exit criteria:

- Data-quality status is visible in UI and persisted logs.
- Fallback/stale/missing contract cases are tested.

---

## Phase 3: Scoring engine

Goal: create meaningful score separation.

Deliverables:

- Deterministic score components.
- Score breakdown.
- Score-compression warning.
- Score unit tests.

Score components:

```text
edge
momentum
liquidity
spread
volatility
regime fit
data quality
time decay risk
```

Exit criteria:

- Top candidate is materially better or compression is flagged.

---

## Phase 4: Ranking engine

Goal: convert scores into ranked opportunities.

Deliverables:

- Global ranking.
- Per-symbol ranking.
- Rank buckets.
- Correlation/duplicate suppression.
- Rank delta tracking.

Exit criteria:

- UI shows top opportunities before debug rows.

---

## Phase 5: Dashboard redesign around truth

Goal: make the UI operationally useful.

Sections:

1. System health.
2. Top opportunities.
3. Executable now.
4. Watchlist.
5. Advisory only.
6. Blocked.
7. Debug table.
8. Audit trail.

Exit criteria:

- Operator can understand best trades in under 30 seconds.

---

## Phase 6: Risk and allocation

Goal: add conservative risk sizing.

Deliverables:

- Position size.
- Max loss.
- Stop loss.
- Target.
- Risk/reward.
- Capital allocation percentage.

Exit criteria:

- No executable trade lacks risk fields.

---

## Phase 7: Paper outcome feedback

Goal: measure whether ranked opportunities work.

Deliverables:

- Outcome labeling.
- Ranked-candidate P/L tracking.
- Hit rate by score bucket.
- Blocker outcome review.

Exit criteria:

- System can show whether higher-ranked candidates actually perform better in paper mode.

---

## Phase 8: Elite opportunity engine

Goal: professional-grade opportunity selection.

Deliverables:

- Regime-aware score weights.
- Portfolio correlation limits.
- Adaptive sizing.
- Drift detection between paper and live-readiness.
- Replay mode.
- Operator daily report.

Exit criteria:

- System behaves like an auditable trading operations console, not a signal printer.

---

## Build order discipline

Do not build phase 8 before phase 0-4 are stable.

Bad order:

```text
ML model -> fancy UI -> auto execution -> maybe fix data quality later
```

Correct order:

```text
data truth -> candidate pool -> scoring -> ranking -> gates -> risk -> feedback -> ML
```

---

## Roadmap warning

More features will not fix a weak scoring engine.

If score separation, fallback demotion, and execution truth are not solid, every advanced layer will amplify garbage.

# AGENTS.md

# Aixion Quant Console / Tradebot Agent Instructions

**Purpose:** Rules for ChatGPT, Codex, or any coding agent working on this repo.

---

## 1. Prime directive

Do not make Tradebot look better by hiding truth.

Your job is to improve:

```text
candidate quality
ranking quality
execution safety
risk clarity
operator visibility
```

Not to create pretty but misleading UI.

---

## 2. Branch rules

Never work directly on `main`.

Use branch names like:

```text
feature/candidate-pool
feature/opportunity-ranking
fix/fallback-execution-demotion
fix/dashboard-ranking-schema
hardening/release-validation
```

---

## 3. Before changing code

Read:

```text
docs/product/PRODUCT_BIBLE.md
docs/product/MVP_SCOPE.md
docs/product/ARCHITECTURE.md
docs/product/ACCEPTANCE_GATES.md
docs/product/FAILURE_LOG.md
```

Then identify which product invariant your change touches.

---

## 4. Non-negotiable invariants

Agents must preserve:

```text
fallback_used == true -> execution_allowed == false
quote_valid == false -> execution_allowed == false
contract_valid == false -> execution_allowed == false
risk_halt_active == true -> execution_allowed == false
```

Breaking these is a P0 defect.

---

## 5. Development behavior

Good agent behavior:

- Make small, focused changes.
- Add or update tests.
- Update docs when behavior changes.
- Preserve runtime truth.
- Explain blockers clearly.
- Prefer deterministic scoring before ML complexity.

Bad agent behavior:

- Patch UI symptoms only.
- Hide fallback/stale rows.
- Recompute execution truth inside dashboard.
- Add auto-execution without risk gates.
- Treat CI passing as proof of trading edge.
- Mix unrelated refactors and product changes.

---

## 6. Required validation

For most changes:

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

For dashboard changes:

```bash
streamlit run dashboard/streamlit_app.py
```

For scoring/ranking changes, add targeted tests.

---

## 7. Product-specific implementation guidance

### Candidate pool work

Must include:

- Candidate schema.
- Lifecycle states.
- Source strategy preservation.
- Snapshot persistence.
- Tests.

### Scoring work

Must include:

- Score breakdown.
- Data-quality factor.
- Liquidity/spread factor.
- Regime factor if available.
- Score-compression warning.

### Ranking work

Must include:

- Top opportunities.
- Watchlist.
- Advisory-only.
- Blocked.
- Duplicate/correlation handling if feasible.

### Dashboard work

Must include:

- Top opportunities before debug table.
- Primary blocker visible.
- Data-quality visible.
- No hidden recomputation of execution truth.

### Risk work

Executable rows must include:

```text
position_size
stop_loss
target
max_loss
risk_reward
```

---

## 8. PR summary template for agents

```markdown
## Summary

## Product invariant touched

## Files changed

## Validation run

## Risks

## Follow-up
```

---

## 9. Agent failure modes to avoid

- Creating a large PR nobody can review.
- Updating docs but not code when user asked for implementation.
- Updating code but not docs when behavior changed.
- Hiding weak data behind filters.
- Treating fallback as clean data.
- Using ML jargon to hide weak deterministic logic.
- Forgetting that this is also a QA/SDET portfolio repo.

---

## 10. Build priority for future agents

Build in this order:

1. Fallback demotion.
2. Candidate pool.
3. Data-quality gate.
4. Scoring breakdown.
5. Ranking buckets.
6. Dashboard sections.
7. Risk fields.
8. Paper outcome feedback.
9. Advanced regime/ML.

Do not skip steps.

---

## 11. Final instruction

If a change makes the dashboard look better but makes the system less honest, reject it.

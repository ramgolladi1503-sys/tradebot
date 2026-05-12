# ACCEPTANCE_GATES.md

# Aixion Quant Console / Tradebot Acceptance Gates

**Purpose:** Define the gates that decide whether the product, a PR, or a release is acceptable.

---

## 1. Gate philosophy

Tradebot is not accepted because it renders rows. It is accepted only when it preserves trading truth.

Every change must protect:

```text
data quality -> candidate truth -> ranking truth -> execution truth -> risk truth -> audit truth
```

---

## 2. P0 gates: must never fail

### Gate 1: Fallback cannot execute

```text
fallback_used == true -> execution_allowed == false
```

Failure severity: P0.

Acceptance examples:

- A recovered/fallback quote appears only as advisory/watchlist.
- A fallback quote never appears under executable-now.

### Gate 2: Stale quote cannot execute

```text
quote_valid == false -> execution_allowed == false
```

Acceptance examples:

- Stale option LTP blocks execution.
- Stale feed produces visible blocker reason.

### Gate 3: Missing contract cannot execute

```text
contract_valid == false -> execution_allowed == false
```

Acceptance examples:

- Missing token blocks trade.
- Resolver fallback is marked clearly and demoted unless explicitly proven safe.

### Gate 4: Risk halt blocks execution

```text
risk_halt_active == true -> execution_allowed == false
```

Acceptance examples:

- Risk halt overrides high score.
- Dashboard shows risk halt as primary blocker.

---

## 3. Product gates

### Gate 5: Candidate pool exists

Acceptance:

- Strategies emit candidates into a normalized pool.
- UI does not depend only on raw strategy rows.
- Candidate lifecycle status exists.

### Gate 6: Score separation exists

Acceptance:

- Ranking creates meaningful score gaps.
- Score compression is detected and displayed.
- Top opportunity has a reason it is top.

### Gate 7: Ranking buckets exist

Required buckets:

```text
TOP_OPPORTUNITY
EXECUTABLE_NOW
WATCHLIST
ADVISORY_ONLY
BLOCKED
```

### Gate 8: Dashboard shows blockers

Every visible candidate must show:

```text
score
rank
candidate_status
execution_status
primary_reason
primary_blocker
```

---

## 4. Technical gates

### Gate 9: CI passes

Minimum:

```bash
PYTHONPATH=. pytest -q
```

### Gate 10: Health gate passes

```bash
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

### Gate 11: Dashboard row model is stable

Dashboard fields must not crash on missing/old data. Missing runtime truth must be shown as unknown or blocked, not silently converted into executable state.

### Gate 12: Release validation exists

Any runtime-sensitive PR must update or satisfy `docs/product/RELEASE_VALIDATION.md`.

---

## 5. Trading-quality gates

### Gate 13: BUY-only bias is diagnosed

If the system emits mostly BUY candidates, it must expose a directional-bias diagnostic.

Acceptance:

- Market regime supports the bias, or
- Strategy bias is flagged.

### Gate 14: Risk fields exist for executable trades

Every executable trade must include:

```text
position_size
stop_loss
target
max_loss
risk_reward
```

### Gate 15: No-trade state is honest

The system must be able to say:

```text
No high-quality executable opportunity exists right now.
```

That is better than weak trade spam.

---

## 6. PR acceptance checklist

Before merge:

- [ ] Branch is not `main`.
- [ ] CI passes.
- [ ] Health gate passes or failure is documented.
- [ ] Fallback execution invariant is preserved.
- [ ] Stale quote invariant is preserved.
- [ ] Missing contract invariant is preserved.
- [ ] Dashboard does not recompute final truth inconsistently.
- [ ] Ranking fields are tested when touched.
- [ ] Risk fields are tested when touched.
- [ ] Docs updated for behavior changes.

---

## 7. Release acceptance checklist

Before release:

- [ ] Candidate pool validated.
- [ ] Ranking snapshot produced.
- [ ] Execution readiness snapshot produced.
- [ ] Feed health snapshot reviewed.
- [ ] Fallback candidates verified as non-executable.
- [ ] Stale candidates verified as blocked.
- [ ] Dashboard renders top opportunities and blockers.
- [ ] No secret or broker credential committed.
- [ ] Release validation recorded.

---

## 8. Rejection rules

Reject the PR/release if:

- Fallback appears executable.
- Stale option LTP appears executable.
- Missing contract token appears executable.
- Top opportunities are just filtered rows.
- All scores are compressed and unexplained.
- Dashboard hides blockers.
- Risk sizing is absent for executable candidates.
- Tests are skipped without honest reason.

---

## 9. Bottom line

Passing tests is not enough.

The product is accepted only when it can prove:

```text
what is best, why it is best, whether it can execute, and what risk is attached
```

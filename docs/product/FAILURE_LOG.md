# FAILURE_LOG.md

# Aixion Quant Console / Tradebot Failure Log

**Purpose:** Capture failures honestly so the same mistake is not repeated.

---

## Failure format

```markdown
## YYYY-MM-DD — Failure title

Severity: P0 | P1 | P2 | P3
Status: Open | Fixed | Monitoring | Accepted risk

What failed:

Impact:

Root cause:

Detection:

Fix:

Validation:

Prevention:
```

---

## 2026-05-12 — UI rows looked active but ranking was weak

Severity: P1
Status: Open

What failed:

The UI could show multiple trade rows, but the rows were too similar and did not prove real opportunity quality.

Impact:

Operator may think the bot is working because rows appear, while the system is only displaying filtered output.

Root cause:

No strong candidate-pool/ranking layer. Confidence values were not enough to separate true top opportunities from noise.

Detection:

Manual UI review showed score compression and similar-looking candidates.

Fix:

Build candidate pool, scoring engine, and ranking engine.

Validation:

- Score separation test.
- Ranking bucket test.
- Dashboard top-opportunity section.

Prevention:

Do not treat visible rows as product success.

---

## 2026-05-12 — Fallback/recovered data appeared too prominent

Severity: P0
Status: Open

What failed:

`recovered_fallback` appeared frequently enough to threaten execution truth.

Impact:

Fallback data can make bad quotes look tradable and destroy execution quality.

Root cause:

Fallback was treated as recovery instead of a data-quality warning.

Fix:

Enforce:

```text
fallback_used == true -> execution_allowed == false
```

Validation:

- Execution gate test.
- Dashboard advisory-only display test.

Prevention:

Fallback must always be visible and demoted.

---

## 2026-05-12 — Product behaved like filtered viewer instead of opportunity engine

Severity: P1
Status: Open

What failed:

System showed survived/emitted rows rather than ranked opportunities.

Impact:

No proper prioritization of capital or attention.

Root cause:

Missing candidate-pool abstraction and ranking lifecycle.

Fix:

Add flow:

```text
strategies -> candidate_pool -> scoring -> ranking -> selection -> execution gate
```

Validation:

- Candidate lifecycle tests.
- Ranking snapshot tests.

Prevention:

No strategy should directly define final dashboard truth.

---

## 2026-05-12 — BUY-side bias not diagnosed

Severity: P2
Status: Open

What failed:

Output appeared heavily BUY-oriented.

Impact:

Could indicate bullish strategy bias, broken bearish filters, or missing market-regime adaptation.

Root cause:

No directional-bias diagnostic tied to regime.

Fix:

Add directional distribution summary and regime comparison.

Validation:

- Test scenario with falling market should produce PE/short-side awareness or bias warning.

Prevention:

Every run should summarize direction distribution.

---

## 2026-05-12 — Capital allocation missing from opportunity output

Severity: P2
Status: Open

What failed:

Trade rows did not consistently show how much to risk or allocate.

Impact:

Operator still has to manually guess sizing.

Root cause:

Risk allocation not first-class in product flow.

Fix:

Add minimum risk fields for executable trades.

Validation:

- Executable candidate cannot be missing stop/target/size.

Prevention:

Execution gate must require risk fields.

---

## Failure severity guide

P0:

- Unsafe execution possible.
- Fallback/stale/missing-contract candidate can execute.
- Risk halt can be bypassed.

P1:

- Product decision quality broken.
- Ranking misleading.
- Dashboard hides truth.

P2:

- Important feature gap.
- Operator must manually compensate.

P3:

- Cosmetic or documentation-only issue.

---

## Open failure backlog

- [ ] Implement fallback demotion invariant.
- [ ] Implement candidate pool.
- [ ] Implement data-quality gate.
- [ ] Implement score separation warning.
- [ ] Implement directional-bias diagnostic.
- [ ] Implement risk fields for executable candidates.
- [ ] Implement dashboard top-opportunity section.

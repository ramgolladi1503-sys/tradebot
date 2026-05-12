# RELEASE_VALIDATION.md

# Aixion Quant Console / Tradebot Release Validation

**Purpose:** Prove a release is safe enough to merge or run.

---

## 1. Release principle

A release is not valid because code compiles.

A release is valid only when it protects:

```text
feed truth
candidate truth
ranking truth
execution truth
risk truth
audit truth
```

---

## 2. Required commands

Run:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

For dashboard changes:

```bash
streamlit run dashboard/streamlit_app.py
```

For data/reconciliation changes when local data exists:

```bash
python scripts/data_qc.py
python scripts/sla_check.py
python scripts/reconcile_fills.py
```

---

## 3. Product validation checklist

- [ ] Candidate pool produces candidates.
- [ ] Data-quality gate classifies candidates.
- [ ] Fallback candidates are not executable.
- [ ] Stale candidates are not executable.
- [ ] Missing-contract candidates are not executable.
- [ ] Ranking creates meaningful score separation or flags compression.
- [ ] Dashboard shows top opportunities first.
- [ ] Dashboard shows blocked/advisory/watchlist sections.
- [ ] Every visible row has primary reason and blocker.
- [ ] Executable rows have risk fields.

---

## 4. Runtime validation checklist

- [ ] Feed health artifact exists.
- [ ] Quote age is visible.
- [ ] Websocket state is visible when applicable.
- [ ] Token subscription count is visible when applicable.
- [ ] Contract resolver state is visible.
- [ ] Risk halt state is visible.
- [ ] Decision audit is persisted.
- [ ] Dashboard uses persisted truth.

---

## 5. CI validation checklist

- [ ] Unit tests pass.
- [ ] Health gate passes.
- [ ] Portfolio CI passes if triggered.
- [ ] No unrelated failing workflow ignored.
- [ ] Any skipped tests are explained.

---

## 6. Safety validation checklist

Reject release if any answer is yes:

- [ ] Can fallback become executable?
- [ ] Can stale LTP become executable?
- [ ] Can missing contract token become executable?
- [ ] Can risk halt be bypassed?
- [ ] Can UI hide primary blockers?
- [ ] Can dashboard recompute different execution truth?
- [ ] Are credentials or sensitive files committed?

---

## 7. Evidence to capture

For every serious release, capture:

```text
branch
commit SHA
test command output
health gate output
dashboard screenshot if UI changed
ranking snapshot sample
blocker distribution
known limitations
rollback plan
```

---

## 8. Release note template

```markdown
## Release summary

## Changed areas

## Validation commands run

## Results

## Runtime-sensitive impact

## Known risks

## Rollback plan

## Screenshots / artifacts
```

---

## 9. Release blocker examples

Release must stop if:

- Top opportunities are fallback-heavy.
- Scores are compressed with no warning.
- Dashboard only shows debug table.
- Executable trades lack stop/target.
- Feed health says stale but UI shows executable.
- Contract resolver fails silently.

---

## 10. Bottom line

A release that looks good but cannot prove execution truth is not a release. It is a risk event.

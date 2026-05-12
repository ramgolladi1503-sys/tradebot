# RUNBOOK.md

# Aixion Quant Console / Tradebot Runbook

**Purpose:** Operational steps for running, validating, debugging, and releasing Tradebot safely.

---

## 1. Golden rule

Do not trust the dashboard first.

Trust this order:

```text
runtime artifacts -> logs -> persisted decision state -> dashboard rendering
```

If the dashboard looks good but runtime truth is bad, the system is bad.

---

## 2. Local setup

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Use paper/offline-safe settings unless intentionally testing live behavior.

```bash
export EXECUTION_MODE=PAPER
export KITE_USE_API=false
```

---

## 3. Standard validation

Run before opening or merging a PR:

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

For dashboard changes:

```bash
streamlit run dashboard/streamlit_app.py
```

---

## 4. Live-readiness checklist

Before any live-market validation:

- [ ] Correct branch checked out.
- [ ] No uncommitted risky changes.
- [ ] Broker credentials are local only.
- [ ] Execution mode is paper unless explicitly intended.
- [ ] Feed health artifact exists.
- [ ] Contract resolver is current.
- [ ] Risk halt state is known.
- [ ] Dashboard renders without schema crash.
- [ ] Fallback candidates are not executable.

---

## 5. Feed debugging

Check:

```text
.runtime/logs/feed_runtime_latest.json
runtime events
quote timestamps
subscribed token count
stale reason
```

Common failures:

- Websocket disconnected.
- Subscribed tokens count is zero.
- Last tick epoch reset to zero.
- Quote age is too high.
- Option LTP stale.
- Depth unavailable.

Response:

1. Confirm feed health source.
2. Confirm token subscription.
3. Confirm latest quote age.
4. Confirm dashboard reads the same feed state.
5. Do not mark candidates executable until feed is clean.

---

## 6. No executable trades debugging

Do not guess.

Check blockers in this order:

1. Feed health.
2. Option LTP freshness.
3. Contract resolution.
4. Fallback usage.
5. Spread/liquidity.
6. Risk halt.
7. Missing stop/target.
8. Score too low.
9. Candidate lifecycle status.

Expected result:

```text
No executable trades
because <specific blocker distribution>
```

Bad result:

```text
No executable trades
reason unknown
```

---

## 7. Fallback debugging

If `recovered_fallback` or fallback quote appears:

- It must be advisory/watchlist only.
- It must not be executable.
- It must show data-quality blocker.
- It must be visible in the UI.

Patch priority if violated: P0.

---

## 8. Ranking debugging

Symptoms of fake ranking:

- Scores all clustered tightly.
- Top row is not materially better.
- Every candidate is BUY.
- Fallback-heavy candidates rank high.
- UI only filters rows.

Response:

1. Inspect score breakdown.
2. Check data-quality weight.
3. Check liquidity/spread penalty.
4. Check regime-fit score.
5. Check directional-bias diagnostic.
6. Check duplicate/correlation suppression.

---

## 9. Dashboard debugging

Dashboard must show truth, not create truth.

Check:

- Input artifact path.
- Row schema.
- Missing columns.
- Timestamp conversion.
- Execution status mapping.
- Blocker display.
- Rank bucket display.

If UI crashes, do not patch randomly. First identify whether the source artifact schema changed.

---

## 10. Release process

1. Create feature/docs branch.
2. Make changes.
3. Run tests.
4. Run health gate.
5. Update relevant product docs.
6. Open PR.
7. Review CI.
8. Validate dashboard if touched.
9. Merge only after gates pass.

Never direct-push risky work to `main`.

---

## 11. Emergency rollback

If a release breaks execution truth:

1. Stop live/paper run.
2. Record failure in `FAILURE_LOG.md`.
3. Identify last good commit.
4. Revert or disable the broken path.
5. Run tests and health gate.
6. Open fix PR.

---

## 12. Daily operator checklist

Before market:

- [ ] Pull latest safe branch.
- [ ] Install dependencies if changed.
- [ ] Validate env.
- [ ] Run health gate.
- [ ] Confirm feed readiness.
- [ ] Confirm contract instruments.
- [ ] Confirm risk state.

During market:

- [ ] Watch feed health.
- [ ] Watch top opportunities.
- [ ] Watch fallback count.
- [ ] Watch blocker distribution.
- [ ] Avoid manual override without evidence.

After market:

- [ ] Save ranking snapshot.
- [ ] Save decision audit.
- [ ] Review outcome labels.
- [ ] Update failure log if needed.

---

## 13. No-BS operator rule

If the system cannot explain why a trade is top-ranked, do not trust it.

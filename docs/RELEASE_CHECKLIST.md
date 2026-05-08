# Tradebot Release Checklist

Use this checklist before merging release-sensitive changes, tagging a release, or using a branch as the source for live-market/paper-market operation.

Tradebot is a real-time fintech reliability project. A release is not safe just because the code starts. It must prove market data, contract resolution, execution gates, risk controls, persistence, dashboard fields, and reconciliation still agree.

For historical context behind these gates, read [Historical engineering log](HISTORICAL_ENGINEERING_LOG.md).

---

## 1. Repository state

- [ ] Branch is based on the latest `main`.
- [ ] Working tree is clean.
- [ ] No generated logs, SQLite DBs, cache files, screenshots with sensitive data, model binaries, or local reports are staged accidentally.
- [ ] No `.env`, broker token, API key, account ID, or private credential is staged.
- [ ] No unresolved merge conflict markers exist.

Commands:

```bash
git checkout main
git pull origin main
git checkout -b release/<short-name>
git status
```

---

## 2. Historical evidence review

Before deciding release readiness, check whether this release touches a past failure pattern from [Historical engineering log](HISTORICAL_ENGINEERING_LOG.md).

- [ ] Execution-intent boundary reviewed if execution routing or review queue changed.
- [ ] Execution truth guard reviewed if candidate status, score, or ranking changed.
- [ ] Fallback candidate handling reviewed if market-data fallback, planning rows, softened rows, or advisory rows changed.
- [ ] Contract-resolution history reviewed if instrument mapping, token resolution, expiry, strike, or CE/PE handling changed.
- [ ] No-executable-trades history reviewed if candidates are visible but not executable.
- [ ] Feed freshness history reviewed if tick store, depth websocket, quote age, DB flush timing, or feed runtime logs changed.
- [ ] Dashboard/persistence history reviewed if review queue fields, normalized rows, final decision fields, or dashboard columns changed.
- [ ] CI/health-gate history reviewed if workflow, test selection, or health artifacts changed.

Evidence to capture in the PR:

```text
Historical PR/issue referenced:
Subsystem affected:
Past failure pattern protected:
Validation evidence:
Remaining risk:
```

---

## 3. Dependency and environment sanity

- [ ] Python dependencies install cleanly.
- [ ] Local environment is paper/offline unless intentionally testing live broker behavior.
- [ ] Required env template exists.

Commands:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
test -f .env.example
```

Safe defaults for local validation:

```bash
export PYTHONPATH=.
export EXECUTION_MODE=PAPER
export KITE_USE_API=false
```

---

## 4. Full test gate

- [ ] Full pytest suite passes.
- [ ] No test requires real broker credentials in CI.
- [ ] Tests do not depend on live-market timing.

Command:

```bash
PYTHONPATH=. pytest -q
```

---

## 5. Offline health gate

- [ ] Deterministic health gate passes.
- [ ] Health report is generated.
- [ ] Health gate does not rely on Kite secrets or real market session.

Command:

```bash
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

Expected artifacts when available:

```text
logs/events.jsonl
logs/recon.json
logs/health_gate_report.json
logs/health_gate_report.md
```

In CI, artifacts may be stored under `.runtime/logs/`.

---

## 6. Runtime-risk review

Complete this section if the PR touches `core/`, `strategies/`, `scripts/`, `dashboard/`, `config/`, `models/`, or `rl/`.

- [ ] Market-data freshness behavior is unchanged or explicitly validated.
- [ ] Stale option LTP behavior is unchanged or explicitly validated.
- [ ] Contract-resolution failures still surface clearly.
- [ ] Safe fallback behavior cannot silently become executable without explicit guardrails.
- [ ] Execution gate statuses still separate executable, queue-only, advisory, and blocked states.
- [ ] Risk halt and kill switch behavior are not weakened.
- [ ] Review queue/dashboard fields are still consistent with persisted runtime output.
- [ ] Reconciliation behavior still catches fills-vs-log mismatch.

Useful targeted checks:

```bash
PYTHONPATH=. pytest -q tests/test_runtime_health_eval.py tests/test_contract_resolution_guard.py tests/test_stale_feed_simulator.py
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

---

## 7. Broker/session-sensitive review

Complete this section if the change touches Kite/broker auth, instruments, feed, websocket, live fills sync, order routing, or execution intents.

- [ ] Paper/offline tests pass first.
- [ ] No credential is printed to logs.
- [ ] `.env.example` remains placeholder-only.
- [ ] Broker unavailable state fails safe.
- [ ] Auth/session failure is visible to the operator.
- [ ] Feed stale/disconnected state blocks or downgrades execution correctly.

Safe validation commands:

```bash
python scripts/check_kite_auth.py
python scripts/validate_kite_session.py
python scripts/download_instruments.py
```

Only run live broker validation when the environment is intentionally configured and you understand the operational risk.

---

## 8. Dashboard and persistence review

Complete this section if the change touches dashboard rendering, review queue, normalized rows, trade log, analytics, or reporting.

- [ ] Dashboard starts locally.
- [ ] Active trades section renders.
- [ ] Entry, stop, target, symbol, strike, side, confidence, and blocker fields are visible where expected.
- [ ] Missing fields fail gracefully instead of crashing.
- [ ] Persisted values are preserved instead of silently recomputed.
- [ ] No fake confidence/ranking drift is introduced.

Commands:

```bash
streamlit run dashboard/streamlit_app.py
PYTHONPATH=. pytest -q
```

---

## 9. Data quality and reconciliation review

Complete this section when touching logs, fills, reports, SQLite persistence, outcome labeling, or data governance.

- [ ] Data QC runs when local data exists.
- [ ] SLA checks run when local data exists.
- [ ] Reconciliation catches mismatches.
- [ ] Hashing/data-manifest scripts are still usable.

Commands:

```bash
python scripts/data_qc.py
python scripts/sla_check.py
python scripts/reconcile_fills.py
python scripts/hash_trade_log.py
python scripts/data_manifest.py
```

---

## 10. Past-release evidence capture

For major fixes or releases, record the evidence in the PR using this structure:

```text
Issue / PR reference:
Original failure:
Subsystem:
Fix summary:
Tests run:
Health gate status:
CI status:
Paper/live validation:
Known limitation:
Rollback path:
```

This is required for changes similar to past work around:

- no executable trades
- contract-resolution fallback
- stale feed / feed freshness
- execution truth guard
- decision-engine promotion path
- dashboard field drift
- risk halt / kill switch
- reconciliation mismatch

---

## 11. CI/release gate status

Before merge, verify GitHub shows green for:

- [ ] `ci / unit_tests`
- [ ] `ci / health_gate`
- [ ] `Portfolio CI / Documentation, architecture, runtime health, contract guard, stale feed, and portfolio quality gate`

Do not merge when required checks are red, skipped, or stale.

---

## 12. Documentation review

- [ ] README still matches actual commands.
- [ ] Architecture links still work.
- [ ] Test report guide still matches CI artifacts.
- [ ] Branch protection policy is current.
- [ ] Historical engineering log is current if the PR fixes a major runtime failure.
- [ ] Known limitations are not hidden.
- [ ] Any runtime-sensitive behavior change is documented honestly.

---

## 13. Final release decision

Only merge/tag/use the release branch when all relevant checks above pass.

If a check fails, do not explain it away. Fix the cause, rerun the checklist, and include the result in the PR.

Trading-system rule: if the system cannot explain why a trade is executable, queue-only, advisory-only, or blocked, the release is not ready.

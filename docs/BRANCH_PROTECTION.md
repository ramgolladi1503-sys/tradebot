# Branch Protection Policy

Tradebot treats `main` as the stable, portfolio-ready branch for the options trading system.

No feature, refactor, dashboard change, broker integration change, strategy change, risk-gate change, or emergency fix should be committed directly to `main`.

This repository is not just a code sample. It contains live-market-adjacent logic for market data, contract resolution, execution gating, review queues, risk controls, dashboard persistence, reconciliation, and broker/session workflows. A careless direct push can break the system silently.

---

## Required protection for `main`

Enable the following GitHub branch protection rules for `main`:

- Require a pull request before merging.
- Require status checks to pass before merging.
- Require branches to be up to date before merging.
- Require conversation resolution before merging.
- Block force pushes.
- Block branch deletion.
- Block direct pushes to `main` by restricting who can push.
- Require linear history if the repo workflow prefers squash or rebase merges.

Recommended additional settings:

- Do not allow bypassing the above settings unless an emergency fix is documented in the PR.
- Require review before merging changes under:
  - `core/`
  - `strategies/`
  - `scripts/`
  - `dashboard/`
  - `config/`
  - `models/`
  - `rl/`
  - `.github/workflows/`
- Require extra review notes for anything touching execution routing, risk halts, Kite/broker auth, market feed freshness, contract resolution, live fills sync, or persisted dashboard fields.

---

## Required status checks

The following checks should be required before merge:

- `ci / unit_tests`
- `ci / health_gate`
- `Portfolio CI / Documentation, architecture, runtime health, contract guard, stale feed, and portfolio quality gate`

These checks exist for different reasons:

- `ci / unit_tests` runs the full pytest suite in paper/offline mode.
- `ci / health_gate` runs the deterministic offline health gate.
- `Portfolio CI` proves the repo still has its architecture docs, portfolio docs, runtime-health tests, contract-resolution guard tests, and stale-feed simulator tests.

---

## Merge policy

Preferred merge method:

- Squash and merge for normal PRs.
- Rebase merge only for clean maintenance-only changes.
- Avoid merge commits unless preserving branch history is intentionally required.

Do not merge if:

- CI is failing.
- The branch is behind `main`.
- Review comments are unresolved.
- The PR mixes unrelated runtime, dashboard, ML, and docs changes.
- The validation section says only "not tested" without a strong reason.

---

## Trading-system quality bar

A PR must clearly explain whether it affects any of these areas:

- Market feed freshness or stale-feed handling.
- Option LTP validation.
- Contract resolution or fallback behavior.
- Strategy signal generation.
- Execution gate or review queue classification.
- Risk halt, kill switch, or soft-kill thresholds.
- Execution router or execution intent logging.
- Live fills sync and reconciliation.
- Dashboard field names, normalized rows, or persisted decision schema.
- ML/RL data generation, model activation, or dataset freezing.
- CI, release gates, or operational scripts.

If the change touches execution, risk, broker auth, contract resolution, or feed handling, the PR must include validation output, not just a description.

---

## Forbidden patterns

Do not merge PRs that:

- Allow fallback market data to become executable without explicit safety reasoning.
- Weaken stale-feed or stale-option-LTP checks.
- Hide contract-resolution failures instead of surfacing them.
- Change persisted dashboard fields without updating tests/docs.
- Commit broker secrets, access tokens, account identifiers, or `.env` contents.
- Add generated logs, local DB files, model binaries, tarballs, screenshots with sensitive data, or cache files.
- Modify dependency files without explaining why.
- Touch live execution behavior without paper/offline validation.
- Skip the health gate for runtime-sensitive changes.

---

## Local pre-merge validation

Minimum validation before opening a normal PR:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

For dashboard or persisted-output changes, also run the dashboard locally:

```bash
streamlit run dashboard/streamlit_app.py
```

For broker/session or live-readiness changes, run only with safe paper/offline settings unless intentionally testing live behavior:

```bash
export EXECUTION_MODE=PAPER
export KITE_USE_API=false
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

For data-quality/reconciliation changes, run the relevant operational checks when local data is available:

```bash
python scripts/data_qc.py
python scripts/sla_check.py
python scripts/reconcile_fills.py
```

---

## Emergency changes

Emergency fixes still require a PR.

The PR must include:

- What broke.
- Why the normal path was insufficient.
- Exact commands run.
- What risk remains.
- Follow-up cleanup issue if the emergency fix is temporary.

No silent direct push to `main` is acceptable.

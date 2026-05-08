## Summary

Describe exactly what changed.

## Why this is needed

Describe the bug, risk, feature, or cleanup this PR addresses.

## Type of change

- [ ] Bug fix
- [ ] Feature
- [ ] Security hardening
- [ ] Runtime reliability
- [ ] Trading/risk logic
- [ ] Market-data/feed handling
- [ ] Contract resolution
- [ ] Dashboard/persistence
- [ ] ML/RL/data workflow
- [ ] CI/release/docs
- [ ] Refactor only

## Tradebot impact area

Check every area touched by this PR:

- [ ] Market feed freshness / stale feed handling
- [ ] Option LTP / quote validation
- [ ] Contract resolver / instrument mapping
- [ ] Strategy signal generation
- [ ] Execution gate / review queue classification
- [ ] Risk halt / kill switch / soft-kill rules
- [ ] Execution router / order intent logging
- [ ] Live fills sync / reconciliation
- [ ] Dashboard fields / Streamlit rendering
- [ ] Trade logs / SQLite / reports
- [ ] Model training / dataset freezing / RL scaffold
- [ ] GitHub Actions / CI / release gate
- [ ] Documentation only
- [ ] No runtime-sensitive behavior changed

## Safety notes

Answer honestly:

- Can this change affect whether a trade becomes executable? Yes / No
- Can this change affect position sizing, risk halt, or kill switch behavior? Yes / No
- Can this change affect live feed freshness, stale LTP, or broker session behavior? Yes / No
- Can this change affect persisted dashboard/review queue fields? Yes / No
- Can this change expose private operational data? Yes / No

Details:

## Validation

Minimum commands for most PRs:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

Commands actually run:

```bash
# Paste exact commands and results here.
```

## Extra validation for runtime-sensitive changes

Use the relevant checks below when applicable:

```bash
PYTHONPATH=. pytest -q tests/test_runtime_health_eval.py tests/test_contract_resolution_guard.py tests/test_stale_feed_simulator.py
python scripts/data_qc.py
python scripts/sla_check.py
python scripts/reconcile_fills.py
streamlit run dashboard/streamlit_app.py
```

Results / screenshots / logs:

## Checklist

- [ ] Branch is based on latest `main`
- [ ] No direct changes were made on `main`
- [ ] No generated logs, local DBs, cache files, or sensitive screenshots are committed
- [ ] No private config or operational credentials are committed
- [ ] README/docs updated if behavior changed
- [ ] Tests added or updated where needed
- [ ] CI passes
- [ ] Portfolio CI passes
- [ ] All conversations are resolved
- [ ] Release checklist reviewed for runtime-sensitive changes

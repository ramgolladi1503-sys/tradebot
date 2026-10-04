# Issue 9 targeted mutation results — 2026-10-03

**source_agent:** gsd
**action:** UPDATE_DOCS
**repository HEAD:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**branch:** `ram/issues-7-11-graph-repair`

## Baseline

Command:

```text
PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/core/test_market_session_store.py::test_store_rejects_bar_before_event_time_completion tests/core/test_market_session_store.py::test_session_store_rejects_mutation_of_completed_bar
```

Result: **2 passed, 1 warning in 1.44s**.

## Mutation run

Command:

```text
python3 scripts/verify_issues_7_11_issue9_mutations.py
```

Result: **2/2 targeted mutants killed**.

- `remove_event_time_completion_cutoff` — the designated incomplete-bar test failed under the mutant.
- `remove_immutable_duplicate_hash_guard` — the designated immutable completed-bar test failed under the mutant.
- The harness rejects timeouts, collection/import errors, and unrelated failures as invalid outcomes.
- Mutations ran against temporary source copies; the runner verified checkout source/test hashes remained unchanged.

SHA-256:

- `core/market_session_store.py`: `50e89cfd40dbfe052773eda008fec23a4dabcebf9c877b4582e4f09341791551`
- `tests/core/test_market_session_store.py`: `95250a1e1496e2206ca0a0c1b3f6e809f9b89496f7fcaf64f29534884c05709b`

## Limits

This closes only the completion-cutoff and immutable-duplicate code mutants. It does not simulate process termination mid-transaction or prove actual service restart/captured-live parity. Issue 9 remains offline-verified with running-service restart and captured/live parity UNKNOWN.

## Continuation — abrupt process termination proof — 2026-10-03

The historical baseline and its two-mutant result above are retained unchanged. A later continuation added a subprocess crash-consistency test and a third code mutant. Current bounded result:

- Test: `tests/core/test_market_session_store.py::test_process_death_before_store_context_commit_rolls_back_insert`
- Command: `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/core/test_market_session_store.py::test_process_death_before_store_context_commit_rolls_back_insert tests/core/test_market_session_store.py`
- Result: **19 passed, 1 warning**.
- Mutation command: `PATH=/tmp/tradebot-test-python-bin:$PATH python3 scripts/verify_issues_7_11_issue9_mutations.py`
- Result: **3/3 mutants killed**: `commit_completed_bar_before_context_exit`, `remove_event_time_completion_cutoff`, and `remove_immutable_duplicate_hash_guard`.
- The child asserts the actual inserted row is visible inside the uncommitted transaction, exits with status 73 before context commit, and the parent verifies no row survived plus `PRAGMA integrity_check=ok`.
- Current SHA-256: `core/market_session_store.py` `50e89cfd40dbfe052773eda008fec23a4dabcebf9c877b4582e4f09341791551`; `tests/core/test_market_session_store.py` `b6eeecce8f89cce1a41ae49e60911eac9317333513c4077f334aaac7e116f3ba`; mutation runner `scripts/verify_issues_7_11_issue9_mutations.py` `8c23aabd2ac4aabed88c783b5b64405aad8a271dc9dd865bae4d1bfd6cab21fb`.

This narrows the earlier stated gap about process termination to one SQLite transaction interruption point. Actual observer-service restart, OS/power-loss guarantees, and captured/live parity remain unverified.

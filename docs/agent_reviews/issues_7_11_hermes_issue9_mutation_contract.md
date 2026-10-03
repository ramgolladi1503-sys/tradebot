# Hermes Addendum — Issue 9 Code-Mutation Proof

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**scope:** Temporary-copy mutation verification of two existing Issue 9 store invariants.

## Finding

Issue 9 has direct persistence, restart, cutoff, deduplication, corruption, and late-tick regressions. It did not have a dedicated harness proving that the cutoff and immutable-duplicate tests detect removal of the corresponding source guards.

## Contract

1. The verifier copies `core/market_session_store.py` and its existing focused test module to a temporary package. All source mutations occur only in that copy.
2. Removing the event-time completion cutoff must be killed by `test_store_rejects_bar_before_event_time_completion`.
3. Removing immutable row-hash comparison for a duplicate primary key must be killed by `test_session_store_rejects_mutation_of_completed_bar`.
4. A mutation counts as killed only when the intended test is collected and fails by assertion. Import errors, collection errors, timeout, or unrelated failure invalidate the result.
5. The harness records SHA-256 for the checkout source and test before and after mutation execution and requires them to remain unchanged.
6. This proves only these two Issue 9 guards. It does not prove actual service restart, captured/live parity, all crash modes, or campaign-wide mutation closure.

## Safety boundaries

No production files are edited by the harness. It does not access market data, start a runtime, call a broker, or create/modify/cancel orders. No execution, paper, live, strategy, risk, freshness, session, or instrument-universe authority changes.

## Acceptance

The baseline tests pass; both isolated source mutants are killed by their designated behavior tests; checkout hashes remain unchanged; and the Issue 9 status remains offline-only with live parity UNKNOWN.

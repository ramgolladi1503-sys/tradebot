# R2 persistence repair handoff

## Authority

- Base SHA: `fd00cbfb2ec06db2df4a5700aedfd93d17132bcf`
- Checkout: `/Volumes/TradeBotData/tradebot-v38b-persistence-repair-20260907`
- Preserved failed-session evidence: `/Volumes/TradeBotData/live-readonly-20260907-r2-v38b-fd00cbfb`
- This checkout has not been used for live observation.

## Problem addressed

R2 showed concurrent SQLite writer contention, skipped depth writes, persistence queue saturation, and a runtime snapshot shutdown race. The repair serializes repository-owned SQLite transaction boundaries within one process and gives runtime persistence a configurable drain deadline.

## Changed files

- `core/sqlite_write_lock.py`: shared re-entrant process-local transaction boundary.
- `core/trade_store.py`: serialize trade/depth-store transactions.
- `core/tick_store.py`: serialize tick-store transactions.
- `core/feed/runtime_store.py`: serialize feed-runtime transactions and use the configurable shutdown deadline.
- `config/config.py`: adds `RUNTIME_PERSISTENCE_SHUTDOWN_DEADLINE_SEC` with default `10.0`.
- `tests/test_sqlite_write_lock.py`: lock serialization and re-entrancy tests.
- `tests/test_sqlite_persistence_contention.py`: concurrent depth/runtime SQLite drain test.

## Verification

- Lock/depth/SQLite/runtime lifecycle suite: `11 passed`.
- Live-truth writer/health suite: `23 passed`.
- Concurrent contention test: `1 passed`.
- Syntax compilation and `git diff --check`: passed.

## Safety boundary

No broker adapter, order path, execution authority, risk gate, feed freshness threshold, strategy threshold, or live launcher was changed. The repair does not grant broker-write or order authority.

## New configuration

`RUNTIME_PERSISTENCE_SHUTDOWN_DEADLINE_SEC` controls the default runtime persistence drain deadline. The default is `10.0` seconds; an explicit function argument remains authoritative for tests and governed shutdown callers.

## Rollout gates

1. Review this isolated diff against the exact base SHA.
2. Run the focused suites with third-party pytest plugin autoload disabled in the validation environment.
3. Promote the repair to a clean governed release; do not modify the preserved R2 checkout.
4. Run a read-only live session with a fresh evidence root and exact release SHA.
5. Require feed persistence queues to remain bounded, SQLite drain/checkpoint proof, canonical candidate handoff, and CAS input/evaluator evidence before declaring success.
6. Keep broker-write, order, paper, and live-execution authority false throughout.

The current R2 session remains `LIVE_SESSION_PARTIAL`; this handoff does not retroactively upgrade it.

# V37 SQLite WAL bound

STATUS: PASS_FOR_TICK_STORE_CONNECTION_CONTRACT

The tick writer now applies `wal_autocheckpoint=1`,
`journal_size_limit=65,536`, and a `wal_checkpoint(TRUNCATE)` after each
committed batch. A busy checkpoint raises `SQLITE_WAL_CHECKPOINT_BUSY` and the
write path records a bounded-storage failure. The policy is applied on every
connection created by the governed `_conn()` boundary.

The input transaction is additionally capped at 1,000 rows and 193,000 logical
serialized row bytes. The contract is covered by
`tests/test_sqlite_wal_bounds_v37.py` and the tick-store regression suite.

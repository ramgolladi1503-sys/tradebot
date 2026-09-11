# V32 SQLite WAL authority

The read-only candidate uses WAL and synchronous NORMAL in tick/runtime stores.
The source inventory does not establish a governed wal_autocheckpoint,
journal_size_limit, checkpoint-after-batch rule, or maximum transaction/WAL
size for all writers. Snapshot export uses bounded backup deadlines, but that
does not prove a WAL peak bound. `WAL_BOUND_DERIVABLE=false` and
`LONG_LIVED_READER_BLOCKER=UNKNOWN`.

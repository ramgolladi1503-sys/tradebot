# V37 SQLite transaction bound

STATUS: PASS_FOR_TICK_STORE

The governed tick transaction admits no more than 1,000 rows and no more than
193,000 canonical logical row bytes. It executes on the one bounded `_conn()`
boundary, which sets WAL mode, normal synchronous durability, one-page
autocheckpointing, a 65,536-byte journal limit, and an immediate truncating
checkpoint. Busy checkpoint results are rejected rather than silently treated
as a successful bounded write.

This contract covers the V37 tick persistence writer. Other SQLite writers
must not be classified as covered without passing through the same boundary.

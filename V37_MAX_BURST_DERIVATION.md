# V37 maximum burst derivation

The bounded queue primitives are derived from fixed queue capacities and
schema/protocol serialization maxima. Depth is `742 * 16,384 = 12,156,928`
bytes. Tick queue is `193 * 10,000 = 1,930,000` bytes. A SQLite input batch
is at most `193 * 1,000 = 193,000` logical row bytes.

These are admission bounds, not proof of SQLite page/index/WAL amplification.
The SQLite and JSONL material-storage bounds remain unresolved and are not
promoted to PASS.

# Upstox 2026-08-04 Corpus Audit and PR #786 Offline Rehearsal

## Objective

Prepare a deterministic, fail-closed audit path for the locally retained Upstox V3 corpus reported for 2026-08-04, and rehearse the PR #786 evidence contracts before another governed Kite live session.

This work deliberately separates two questions:

1. **Does the audit and rehearsal tooling behave correctly?**
2. **Does the real Mac-local corpus pass that tooling?**

The first question is closed offline by CI fixtures. The second remains unexecuted because the raw zstd, normalized Parquet, replay SQLite, and sealed evidence files are not present on GitHub or in the connected runtime.

## Implemented audit contracts

### Immutable source boundary

The runner snapshots each protected source artifact before and after the audit using:

```text
exists
file type
size
mtime_ns
SHA-256
```

The audit root must be separate from both the raw capture root and final evidence root. A source mutation fails closed.

### Raw zstandard audit

The audit:

- enumerates `.zst` files;
- streams every file through zstandard decompression;
- records compressed and decompressed byte counts;
- calculates each file's SHA-256;
- reports every decompression failure.

The current generic runner does not decode Upstox Protobuf frame boundaries. Therefore it does not independently reproduce the claimed `143,646` frame count by itself.

### Normalized Parquet audit

The audit reads every normalized file with:

```python
pq.read_table(path, partitioning=None)
```

It records:

- file and row counts;
- file SHA-256;
- schema fingerprints;
- timestamp fields and span;
- instrument identity fields and coverage;
- read failures.

This prevents Hive directory inference from silently creating conflicting schema columns.

### Manifest lineage audit

The audit recursively extracts file references from compact manifests and independently verifies:

```text
referenced path exists
SHA-256 matches
size matches when declared
```

A summary manifest is not treated as proof unless its referenced raw and normalized files resolve and match.

### SQLite replay audit

SQLite databases are opened in read-only URI mode. For every user table, the audit computes:

```text
row count
ordered row-stream SHA-256
```

Two replays pass only when their table identities, row counts, ordered row hashes, and database semantic hashes match.

### Row reconciliation

The audit does not use the invalid equation:

```text
normalized rows = tick rows + depth rows
```

A normalized market event may produce both a tick row and a depth snapshot. The runner therefore compares normalized rows with tick rows and requires every non-tick difference to be explicitly explained. Depth rows are reported as an overlapping output domain.

### Completed interval identity

The runner extracts canonical interval endings from the constituent-bars Parquet and fails on duplicate interval identities.

The current generic runner does not reconstruct the missing seven intervals from raw ticks or classify each skipped boundary. That remains corpus-specific work after the local corpus is accessible.

### PR #786 offline rehearsal

For every accepted interval, the rehearsal writes one:

```text
authority snapshot
MEG traversal ledger row
MEG export-contract rehearsal row
```

The outputs are append-only and canonically sealed with:

```text
artifact_manifest.json
SHA256SUMS
SEALED
```

Every generated row explicitly states:

```text
source=upstox_replay
offline_replay=true
live_source=false
contract_rehearsal=true
not_certification_evidence=true
read_only=true
broker_write_authority=false
order_authority=false
allowed_for_live_execution=false
allowed_for_paper_execution=false
```

The rehearsal export ledger proves schema durability, interval uniqueness, and sealing behavior. It is not a market signal and cannot satisfy a live Kite MEG gate.

## Focused validation

Validated on implementation head `475817aa93f6dbfe5b9a8f775f2971dff35b0798`.

Forward order:

```text
6 Upstox corpus audit tests passed
5 PR #782 remaining-evidence tests passed
11 total
```

Reverse order:

```text
5 PR #782 remaining-evidence tests passed
6 Upstox corpus audit tests passed
11 total
```

Additional results:

```text
changed modules compiled
protected runtime drift=false
diff check passed
Agent Review Evidence Gate passed
gitleaks passed
```

## Tested negative controls

- corrupt manifest target fails hash verification;
- changed replay content changes the database semantic hash;
- unexplained normalized-versus-tick rows fail reconciliation;
- depth rows are not incorrectly added to tick rows;
- duplicate bar interval identity fails closed;
- nonempty rehearsal output root is rejected;
- all offline rows retain `live_source=false`;
- post-seal ledger mutation fails verification.

## Real corpus execution status

The following reported local state is not remotely accessible:

```text
worktree: /Users/madhuram/tradebot-upstox-replay-quality-capture-v1
branch: data/upstox-replay-quality-capture-v1
reported commit: ce1d9737c8eb99de6ae8761848130a2317a28096
raw root: /Users/madhuram/tradebot/.runtime/market_data/upstox_replay_capture_v1/2026-08-04/093005
evidence root: runtime/market_data/upstox/20260804/full_day_replay_v1
```

The branch and reported final commit are not present on GitHub. Consequently, this work does not independently verify:

- `143,646` decoded frame count;
- `1,041,828` normalized events;
- `1,041,807` replay ticks;
- `10,352` depth snapshots;
- the 21-row difference;
- `353` accepted intervals;
- the seven skipped-boundary reasons;
- zero leadership events;
- the reported local inventory hash.

## Verdict

```text
PASS_UPSTOX_CORPUS_AUDIT_TOOLING_OFFLINE
REAL_CORPUS_AUDIT_NOT_EXECUTED
LOCAL_CORPUS_EXECUTION_REQUIRED
```

Also:

```text
NOT_A_KITE_LIVE_CERTIFICATION
NOT_AN_OPTION_CORPUS
NO_STRUCTURAL_EDGE_CLAIM
FRESH_GOVERNED_KITE_SESSION_STILL_REQUIRED
```

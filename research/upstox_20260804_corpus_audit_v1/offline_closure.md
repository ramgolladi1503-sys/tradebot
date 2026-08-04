# Upstox 2026-08-04 Corpus Audit — Offline Closure

## Verdict

```text
PASS_UPSTOX_CORPUS_AUDIT_TOOLING_OFFLINE
REAL_CORPUS_AUDIT_NOT_EXECUTED
LOCAL_CORPUS_EXECUTION_REQUIRED
```

## What passed

Implementation validated at:

```text
475817aa93f6dbfe5b9a8f775f2971dff35b0798
```

Focused workflow:

```text
run: 30914476277
job: 92008989354
```

Forward order:

```text
6 Upstox audit tests passed
5 PR #782 evidence-contract tests passed
11 total
```

Reverse order:

```text
5 PR #782 evidence-contract tests passed
6 Upstox audit tests passed
11 total
```

Additional gates:

```text
compile passed
protected runtime drift=false
diff check passed
Agent Review Evidence Gate passed
gitleaks passed
```

## What the tooling proves

- source evidence can be snapshotted and checked for mutation;
- zstandard chunks can be decompressed and hashed;
- normalized Parquet can be read without Hive schema inference;
- manifest file references can be independently hash-verified;
- SQLite replays can be compared using ordered table-stream semantic hashes;
- normalized/tick differences fail until explicitly explained;
- depth rows are treated as an overlapping output domain;
- duplicate interval identities fail closed;
- PR #786 authority and MEG ledgers can be rehearsed append-only;
- the rehearsal can be sealed with `artifact_manifest.json`, `SHA256SUMS`, and `SEALED`;
- every rehearsal artifact remains explicitly offline and non-live;
- post-seal mutation fails verification.

## What remains unavailable

The million-row Upstox corpus, its raw zstd chunks, replay databases, and reported local branch/commit remain on the user's Mac and are not available through GitHub or the connected execution environment.

Therefore the following reported values were not independently executed or certified:

```text
143,646 frames
1,041,828 normalized events
1,041,807 replay ticks
10,352 depth snapshots
21-row difference
353 accepted intervals
7 skipped boundaries
0 leadership events
inventory hash 68eb2b71...
```

## Boundaries

```text
NOT_A_KITE_LIVE_CERTIFICATION
NOT_AN_OPTION_CORPUS
NO_STRUCTURAL_EDGE_CLAIM
FRESH_GOVERNED_KITE_SESSION_STILL_REQUIRED
```

The draft PR must not be merged until the runner is executed against the Mac-local corpus and the generated `final_report.json` is reviewed.

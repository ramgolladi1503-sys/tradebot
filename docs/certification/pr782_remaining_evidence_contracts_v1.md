# PR #782 Remaining Evidence Contracts v1

## Scope

This change closes only the three evidence-contract gaps exposed by the governed Kite read-only session on 2026-08-04:

1. canonical PR #782 seal markers;
2. durable authority snapshot evidence;
3. durable cumulative MEG traversal/export evidence.

The previous evidence root remains immutable and is not retroactively certified.

## Previous failed gates

The 2026-08-04 live runtime completed an uninterrupted 16,935.66-second session with zero restarts, zero broker writes, zero order actions, fully reconciled tick/depth/runtime persistence, and lifecycle `CLOSED`.

PR #782 nevertheless failed closed because:

- `artifact_manifest.json`, `SHA256SUMS`, and `SEALED` were absent;
- no authority snapshot artifact existed;
- an early MEG export was overwritten by later latest-cycle duplicate/rejection evidence, so cumulative traversal/export was not provable.

## Gap A — Canonical sealing

`script/seal_pr763_read_only_evidence.py` delegates to the repository's existing canonical sealer in `core.unified_live_validation_pr748_756.seal` and immediately verifies the result with `verify_sealed_evidence_root`.

A successful seal creates exactly the verifier-required contract:

```text
artifact_manifest.json
SHA256SUMS
SEALED
```

The sealer refuses an already or partially sealed root. Existing verifier negative controls prove post-seal mutation fails hash authority.

## Gap B — Authority evidence

`core.read_only_live_evidence.write_authority_snapshot_bundle` reuses the existing PR #771 runtime authority cutover logic. It writes:

```text
authority_snapshots.jsonl
```

as the append-only interval ledger, and:

```text
authority_snapshot.json
```

as the latest verifier-compatible snapshot.

Each row records stable run/session/interval identity, authority buckets, read-only denial fields, producer commit, and a deterministic semantic hash.

The observer emits authority evidence once per newly observed completed index interval. If no canonical interval is produced, finalization writes an explicit empty snapshot rather than fabricating candidates.

Existing PR #782 negative controls continue to reject unsafe executable fallback rows and any session evidence with order authority.

## Gap C — MEG traversal and export evidence

The observer now writes:

```text
meg_traversal_events.jsonl
meg_live_source_exports.jsonl
meg_wiring_evidence.json
```

The first two files are append-only certification truth. The last file is only a latest/cumulative convenience summary.

`MegIntervalScheduler` evaluates a completed index interval at most a bounded number of times. Retryable interval-alignment failures are bounded; successful exports and duplicate-terminal results stop further attempts for that interval.

A successful export remains present in `meg_live_source_exports.jsonl` even when later cycles reject or classify duplicates. The cumulative session export count is derived from the append-only export ledger, not from the latest-cycle result.

No MEG scoring, graph semantics, thresholds, feed behavior, strategy behavior, or risk logic changed.

## Offline positive controls

The focused suite proves:

- canonical marker creation and verifier acceptance;
- append-only authority history and latest-snapshot compatibility;
- successful MEG export survives a later duplicate cycle;
- duplicate polling cannot create a second successful export row;
- misalignment retries are bounded;
- a causally assembled synthetic root passes PR #782 end to end.

## Offline negative controls

The existing verifier suite additionally proves:

- missing MEG semantics remain pending rather than producing a false pass;
- post-seal mutation fails hash authority;
- unsafe fallback data cannot enter the executable authority bucket;
- any order authority in session evidence fails closed;
- deterministic certificate output is stable.

## Commands and results

GitHub Actions workflow:

```text
PR782 Remaining Evidence Contracts
run_id=30904439706
job_id=91976101114
```

Primary order:

```text
9 observer runtime tests passed
5 remaining-evidence contract tests passed
7 PR #782 verifier tests passed
21 passed total
```

Reverse order:

```text
7 PR #782 verifier tests passed
5 remaining-evidence contract tests passed
9 observer runtime tests passed
21 passed total
```

Additional results:

```text
changed modules compiled
protected_runtime_drift=false
git diff --check passed
Agent Review Evidence Gate passed
```

## Explicitly unchanged

This work does not alter:

```text
Kite authentication
subscription universe
FULL-mode handling
tick/depth/runtime persistence
shutdown order
broker or execution modules
order routing
strategy logic
risk logic
capital policy
```

## Offline verdict

```text
PASS_PR782_REMAINING_GAPS_OFFLINE
FRESH_GOVERNED_KITE_SESSION_REQUIRED
```

Offline closure does not certify the previously sealed session and does not prove live success of the new artifacts.

## Remaining live requirement

One fresh governed Kite market-hours session must prove, in the same evidence lineage:

- 51-token subscription/FULL truth;
- completed constituent and index bars;
- append-only authority snapshots;
- at least one append-only successful live-source MEG export;
- persistence reconciliation and graceful shutdown;
- canonical seal markers;
- `PASS_READ_ONLY_POST_MARKET_RELIABILITY`;
- PR #783 certificate assembly only after PR #782 passes.

No profitability, structural-edge, trade-quality, execution-quality, or autonomous-trading claim is made.

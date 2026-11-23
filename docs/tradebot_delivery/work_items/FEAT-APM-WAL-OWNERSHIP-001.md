# Work Item: FEAT-APM-WAL-OWNERSHIP-001

## Identity

- Work Item ID: `FEAT-APM-WAL-OWNERSHIP-001`
- Type: `FEATURE`
- Parent Epic: `EPIC-APM-WAL-DURABILITY-001`
- Parent Feature: none
- Title: Stable single-writer ownership for APM WAL files
- Current State: `DESIGN_READY`
- Priority: `HIGH`

## Business Goal

Ensure that each supported effective APM WAL has one manager owner for its lifetime, including when the WAL is atomically replaced or opened through equivalent supported path aliases.

## Current Behavior

The APM derives a lock path by appending `.lock` to the resolved WAL path. A second manager can use that sidecar itself as its WAL and atomically replace it. The first manager then holds a lock on the old inode while a third manager locks the replacement inode.

## Expected Behavior

Use a persistent ownership identity in a namespace that WAL replacement cannot overwrite. Resolve supported path aliases to the same identity, reject unsupported hard-link aliases, fail closed on lock or filesystem errors, and acquire ownership before recovery/admission.

## In Scope

- Stable lock identity and lifetime for APM WALs.
- Fail-closed path validation and lock acquisition.
- Offline tests for aliases, namespace collision, concurrency, replacement, release, process death, recovery, and unsupported locking.
- Evidence bounded to the tested filesystem.

## Out of Scope

- Multiwriter WAL design.
- Strategy or threshold changes.
- Broker, order, credential, live configuration, deployment, or production process changes.
- Claims of trading performance or live readiness.

## Acceptance Criteria

1. A pre-fix independent-process reproduction shows sidecar replacement permits a second owner.
2. The fix blocks the collision before recovery or WAL mutation and preserves the held lock inode.
3. Relative, dot-segment, parent-symlink, and leaf-symlink aliases cannot obtain a second owner.
4. Hard-linked WAL files fail closed; ordinary atomic WAL replacement leaves the lock inode stable.
5. Concurrent startup admits exactly one owner; release and abnormal termination permit safe recovery by a successor.
6. Unsupported `flock`, lock-open failures, nonregular paths, and reserved lock namespace paths fail closed.
7. The R3 test set is rerun against exact source hashes. Existing hardening003 baseline failures are classified separately.
8. Deployment filesystem remains `DEPLOYMENT_UNVERIFIED` unless the actual mount is identified and tested.

## Safety / Risk Constraints

- Broker/order calls: prohibited.
- SIM/PAPER/LIVE behavior: unchanged; no live authorization.
- Risk gates and feed freshness: unchanged.
- Any lock ambiguity blocks recovery/admission.

## Rollback

Revert only the scoped APM ownership and regression-test changes after stopping all managers that use the new namespace. Preserve existing WAL and lock artifacts; do not delete ownership files while a manager may be active.

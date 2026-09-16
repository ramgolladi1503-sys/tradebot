# Governed Release Rebootstrap V1

`rebootstrap-*` is an exceptional recovery path for a release store whose active head is explicitly quarantined by repository policy. It is not a normal promotion shortcut.

## Preconditions

- Existing release store and readable append-only history.
- Current active SHA is in `SYNTHETIC_INVALIDATED_SHAS`.
- Exact candidate is the checked-out clean commit and is not quarantined.
- Dependency evidence is complete and unresolved-free.
- Full BASE + BOUNDED + CRITICAL gate set has candidate-bound governed primitives.
- Independent `verify_release_rebootstrap_v1` attestation binds candidate, predecessor event/SHA, gate set, primitive hashes, dependency graph, certification, reason and rollback status.

## Journal semantics

A successful transition appends schema-v2 `GOVERNED_REBOOTSTRAP`. Existing events are retained byte-for-byte. The event binds the quarantined predecessor but deliberately has no executable fallback:

```text
fallback_live_sha=null
rollback_status=NO_TRUSTED_FALLBACK
```

A rebootstrap cannot be performed from a healthy head or from another rebootstrap event. Normal certification resumes from the new healthy authority after recovery.

## CLI

```text
scripts/release_manager.py rebootstrap-certify ... --reason <reason>
scripts/release_manager.py rebootstrap-verify ...
scripts/release_manager.py rebootstrap-promote ...
```

Promotion must never be run before independent verification. Manual editing of `current.json` remains prohibited.

## Safety

This subsystem has no broker or order authority. Rebootstrap is release-governance state only and does not claim live readiness, execution viability, prospective evidence, or structural trading edge.

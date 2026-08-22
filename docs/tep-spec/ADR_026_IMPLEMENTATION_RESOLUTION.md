# ADR-026 Resolution — Local Transactional Database Engine

Status: ACCEPTED_FOR_TEP_V1_IMPLEMENTATION_CANDIDATE
Date: 2026-08-22
Authority: frozen Phase-0 ADR-026 constraints + M1–M10 implementation authority.

Decision: use Python stdlib SQLite for the v1 local transactional state/event/evidence index.

Why: local transactional semantics, atomic commits, WAL/recovery support, migrations/backup, no external service dependency, native Python compatibility and explicit corruption/error handling. This is a storage implementation choice, not source/evidence authority.

Alternatives deferred: JSON files fail the transactional requirement; remote DB adds unnecessary infrastructure; another embedded engine would add a dependency without demonstrated need.

Constraints: foreign keys enabled; busy timeout; transactions explicit; schema versioned; state and event writes sharing a transition are atomic; database failure never converts UNKNOWN/MISSING to success; large immutable evidence remains external by reference/hash.

Rollback: storage adapter remains behind TEP interfaces; export/migration tooling must preserve IDs/hashes before replacement.

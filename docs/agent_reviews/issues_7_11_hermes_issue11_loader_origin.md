# Hermes Addendum — Issue 11 canonical feed-truth loader origin

**source_agent:** hermes
**action:** DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**scope:** Offline persisted-feed loader-to-ranking contract only.

## Finding

An independent verifier removed every classifier-recognized snapshot field from a stale `feed_truth_latest.json` payload and added legacy `feed_ok=true`, connected websocket state, and fresh legacy LTP age. `_load_cycle_feed_truth_payload` returned an untyped mapping without retaining that it came from the dedicated versioned snapshot path. Ranking accepted the legacy mapping and returned one executable rank.

The canonical `feed_truth_latest.json` path is written by the v1 feed-truth snapshot writer. Path origin is available to the loader but is not currently carried to classification.

## Contract

1. The loader adds a reserved `feed_truth_loader_origin` field after reading the canonical `feed_truth_latest.json` path. It overwrites any same-named field from file contents. The value identifies the loader path only; it must not claim the serialized payload is authentic or valid.
2. Classification treats this loader-origin marker as a requirement to validate the persisted snapshot contract even if all payload-controlled source, writer, schema, and freshness markers are removed.
3. The existing source/version, required boolean component, producer-time age, maximum-age, websocket, global-block, and freshness checks still apply. Missing or unsupported source must hold; the loader must not repair or synthesize source fields.
4. Explicit legacy mappings from callers without canonical-file origin retain existing compatibility rules.
5. The marker is diagnostic metadata only. It grants no freshness, candidate identity, execution, paper, broker, or order authority.
6. The canonical artifact loader and ranking remain read-only. No producer schema, strategy behavior, candidate dependency declaration, risk gate, or token-universe change is in scope.

## Acceptance proof

- Before the fix, a marker-stripped canonical artifact with injected `feed_ok=true` reproduces a nonzero rank.
- After the fix, the actual loader overwrites a payload-injected origin marker with canonical path metadata and ranking fails closed because snapshot source/freshness evidence is missing or unsupported.
- A normal stale v1 canonical artifact remains held.
- A healthy v1 canonical artifact still passes all existing v1 checks.
- A noncanonical legacy mapping retains explicit legacy behavior.
- An isolated mutation removing the loader-origin assignment is killed by the marker-stripping regression test.
- The focused feed/ranking/runtime compatibility suite passes.

## Safety boundaries and rollback

No execution authority is widened. Global transport/recovery/auth blockers remain unchanged. Candidate-level selective unholding remains explicitly outside scope because score records do not contain authoritative exact dependency identity and freshness.

Rollback the loader-origin assignment, classifier origin check, regression test, and mutation harness together. A rollback restores the reproduced marker-stripping bypass.

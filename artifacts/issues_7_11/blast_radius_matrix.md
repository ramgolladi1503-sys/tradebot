# Issues 7–11 blast radius

Repository base SHA: `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`. All work remains an uncommitted isolated-worktree diff.

| Patch node | Direct callers | Transitive consumers | Runtime artifacts changed | Safety invariants touched | Existing/new tests | Cross-issue risk |
|---|---|---|---|---|---|---|
| Issue 9 MEG completed-bar store | `kite_depth_ws.on_ticks` → shadow tick recorder; observer lifecycle → completed-bar accessor | MEG interval scheduler and observer evidence only | Same-date SQLite bar rows; T5 completion/persistence diagnostics | event-time completion, session date, provenance, no callback DB I/O, no execution authority | Store, buffer, bridge, observer and certification suites; restart/cutoff/concurrency attacks | Must not feed recovered bars into current liveness or CAS source-event authority; normal C1/C2 path remains unresolved |
| Issue 10 advisory source routing | Read-only observer → runtime snapshot producer; producer → explicit run-local JSONL path | Advisory latest and downstream session/EOD readers | Advisory snapshot source path/state/notes and rows from that same ledger | no decision regeneration, no execution eligibility change, no partial JSONL acceptance | Producer and observer tests; path override, partial tail, invalid UTF-8 | One-cycle visibility delay remains; no duplicate mirror is introduced; EOD parity is not certified |
| Issue 11 read-only observer quote truth | observer shadow snapshot builder joins wrapped health and market quote rows | strategy-shadow observation only | shadow snapshot health and quote-freshness/executable-quote fields | observer never grants executable quote authority; candidate safety and global blockers unchanged | shadow adapter, replay, observer event-time attack | Candidate-level isolation and captured cause remain UNKNOWN |
| Issue 11 persisted aggregate ranking truth | runtime snapshot loader → ranking feed-hold gate → shared feed-truth classifier | aggregate candidate-ranking hold only; no per-candidate dependency isolation | ranking hold decision from `feed_truth_latest.json`; configurable snapshot-age limit | stale, malformed, contradictory, unsupported, or missing health authority fails closed; no execution authority change | serialized producer/loader ranking contract, adversarial source/component/time/age tests, compatibility suites | Captured/live parity and candidate-level isolation remain UNKNOWN |
| Issues 7–8 | No code patch | T-1 loader/strategy readiness; CAS heritage loader | No runtime artifact changed | source provenance, calendar, anti-lookahead and exact source-event identity preserved | Heritage/T1 authority tests only prove fail-closed contracts | No synthetic data or candle-to-CAS reconstruction; UNKNOWN retained |

## Patch surfaces

- **Expected:** same-session MEG shadow persistence; observer advisory source selection and partial-tail state; read-only observer snapshot normalization and persisted aggregate ranking-truth validation only.
- **Must not change:** broker/order/risk/kill-switch authority, strategy thresholds/calculations, candidate ranking, token-universe configuration, timestamp semantics, session boundaries, fee/cost logic, Issues 1–6 behavior, unrelated research code.
- **Observability:** bar persistence provenance/latency; advisory source path and source state; feed-health blockers/domains.
- **Rollback:** remove session-store binding for Issue 9; remove explicit Issue 10 source override and retain desk fallback; revert the Issue 11 observer normalization/event-time changes or persisted ranking-truth validation under their respective contracts; preserve global blockers.


## Issue 10 failed-append no-truncate refinement

| Patch node | Direct callers | Transitive consumers | Runtime artifacts changed | Safety invariants touched | Existing/new tests | Cross-issue risk |
|---|---|---|---|---|---|---|
| `core/locked_jsonl.py` failure handler | observer candidate-decision writer; reject-shadow candidate-decision writer | bounded advisory JSONL reader; advisory projection; EOD analytics | failed append can leave incomplete bytes; handler logs and never truncates | foreign bytes are not destructively removed; malformed advisory row rejected; original write error preserved | focused observer/reject-shadow/runtime-snapshot/EOD tests; Issue10 destructive-truncate mutant | Issue10 only; external writer atomicity and foreign-row salvage remain UNKNOWN |

Must-not-change surface: successful append schema/bytes, cooperating flock serialization, decision generation/ranking, routing, strategy/feed/risk behavior, broker/order authority, token universe, and Issues 1–6. Rollback of any future change must preserve the no-truncate invariant unless writer ownership is redesigned and re-specified.

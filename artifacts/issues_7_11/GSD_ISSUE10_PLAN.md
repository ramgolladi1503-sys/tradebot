# GSD MAP → SPEC → PLAN — Issue 10 observer advisory source

## MAP

The observer appends accepted candidate decisions to `output_root/candidate_decisions.jsonl` and calls `produce_and_store_runtime_snapshots` in that same process. The producer's fallback path is derived from `logs_dir()/desks/<DESK_ID>/candidate_decisions.jsonl`, so it does not read the observer's session ledger. The pre-existing desk fallback remains the default for ordinary orchestrator cycles.

## SPEC

Allow the snapshot caller to supply its already-owned decision-ledger path. The observer passes its session-local `candidate_decisions.jsonl`; no row copy or second write is permitted. Read only newline-terminated JSONL records. If the file ends in an unterminated record, exclude that final fragment, preserve preceding complete records, and expose the condition in source state/notes. Legacy callers that omit the override retain the configured desk fallback.

## PLAN

1. Add optional source-path plumbing to `produce_and_store_runtime_snapshots` and `_build_advisory_latest_payload`.
2. Pass `output_root / "candidate_decisions.jsonl"` from the observer call site.
3. Make the advisory tail reader discard an unterminated trailing JSONL record and report the partial tail.
4. Test explicit run-local source selection, normal desk fallback compatibility, partial-tail exclusion, and visibility after the final newline is appended.
5. Run observer, advisory producer, and related serialization/telemetry regression tests; inspect order/broker authority and decision-generation surfaces.

## Re-attack addendum — concurrent file mutation

1. Read from a single open descriptor and bound the read to the descriptor size captured at start.
2. Compare descriptor identity and mutation metadata before/after reading; if the file changed in place during the read, reject the snapshot as `READ_ERROR` and expose no rows.
3. Remove the unterminated raw final fragment before filtering blank lines, so whitespace-only tails cannot drop the preceding complete record.
4. Split only on LF (and strip CR for CRLF); Unicode separators inside valid JSON string values are not record delimiters.
5. Exercise append and same-size truncate/rewrite during read, complete-row/whitespace-tail input, U+2028 string content, and an overlong record with no boundary in the bounded read window.
6. Require EOD accepted-row parity separately; this source-reader repair does not establish it.

## Blast radius

- **Direct caller:** read-only observer runtime; ordinary orchestrator keeps default behavior.
- **Transitive consumer:** advisory latest snapshot and downstream dashboard/EOD reader.
- **Runtime artifact:** advisory snapshot source path/state/notes only.
- **Safety invariants:** no decision generation or execution authority changes; observer remains read-only and non-executable.
- **Rollback:** remove the explicit path argument at the observer call site; the old desk fallback remains available.
- **Cross-issue risk:** Issue 7–9 and 11 data/health/strategy paths must remain byte/behavior unchanged.

## GSD acceptance gate

An observer fixture with a populated run-local decision ledger and absent desk log must yield its row with the run-local source path. A partial appended tail must not be accepted; after newline completion, the row becomes visible. A caller without an override must continue reading the desk fallback. No claim is made that advisory routing caused upstream zero candidates.

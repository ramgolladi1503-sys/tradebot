# PR813 feed runtime required-field trace

- Input SHA: `257d1f477c3b302b57821b8c7f63cf5ade347741`
- Failed session: `pr813-final-rereview-smoke-20260814-103806`
- Failed artifact: `runtime/logs/feed_runtime_latest.json`
- Validator: `core.feed.artifact_loader.load_current_feed_runtime -> _load`
- Missing field: `truth_lineage`
- Producer: `core.kite_depth_ws._write_feed_runtime_snapshot` and
  `core.feed.runtime_store._canonical_runtime_artifact_payload`
- Mutator: `stamp_feed_runtime_provenance`
- Persister: atomic JSON writers for `feed_runtime_latest.json`
- Reader/verifier: `load_current_feed_runtime`, then `validate_truth_lineage`

The failed artifact contained current `run_id`, `boot_epoch`, `feed_epoch`,
writer, schema, `produced_at`, `feed_ok`, and a valid snapshot hash, but no
`truth_lineage`. The runtime writer attempted to bind lineage only when a
pre-existing `feed_truth_latest.json` was present. On the first startup
snapshot that file did not exist, so the producer persisted an unbound
artifact. The validator correctly failed closed with `MISSING_REQUIRED_FIELD`.

The repair publishes a canonical truth snapshot from the current runtime
observation before stamping runtime lineage, using the existing truth builder
and writer. No defaults are substituted for missing runtime fields.

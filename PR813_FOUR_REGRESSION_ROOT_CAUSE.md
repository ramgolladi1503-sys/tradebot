# Four regression root cause

All four nodes failed identically on `11855d1f5` and `56a9bd85d`. The audit repair changed only audit validation/bootstrap files and audit tests; it did not touch these tests, the Phase 2 adapter, or feed-truth production code.

The two local helper functions wrote partial runtime artifacts. They stamped a runtime hash but did not create the paired canonical truth artifact and complete lineage/currentness contract. The production loader correctly failed closed. The helpers now reuse `tests.fixtures.canonical_feed_factory.make_valid_canonical_feed_pair()` and recompute the hash only after adding the test-specific runtime fields.

Classification: four `PRE_EXISTING_FIXTURE_CONTRACT_FAILURE`; source defects proven: zero.

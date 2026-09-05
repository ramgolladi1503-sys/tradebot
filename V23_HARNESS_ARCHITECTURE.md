# V23 Harness Architecture

`ControlledRuntimeHarness` controls only temporary filesystem and clock
boundaries. It invokes the production snapshot producer, canonical
coordinator, consumer, CAS evaluator, readiness writer, primitive store, and
verifier. It does not implement signal logic or reconstruct runtime outputs.

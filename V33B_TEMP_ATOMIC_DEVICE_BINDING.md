# V33B temporary and atomic binding

Startup uses a same-directory temporary probe. The SQLite/Parquet exporter uses `NamedTemporaryFile(dir=output_dir)`. The launcher now rejects an unvalidated runtime root before any material initialization. Unscoped offline `tempfile` calls remain out of the live dependency closure and are not live authority.

`CORE_TEMP_EXTERNAL_BOUND=true` for the governed launcher; `ATOMIC_TEMP_SAME_DEVICE_PASS=true` for the explicit exporter output directory.

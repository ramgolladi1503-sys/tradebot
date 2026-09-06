# V37 Parquet authority

Parquet is a derived optional output and is not required for core runtime
durability. The exporter must be skipped under low-disk pressure. Its current
temporary-file maximum is not independently derived, so it is not a core
storage PASS and cannot be included in the material bound total.

# V37 independent low-disk validator

The low-disk contract remains fail-closed and read-only. It must verify the
configured runtime device, free-space reserve, external mount identity, and
that optional Parquet output is skipped under pressure. Existing low-disk
negative controls remain part of the 118-node authority.

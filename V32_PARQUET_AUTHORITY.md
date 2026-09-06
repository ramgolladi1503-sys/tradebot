# V32 Parquet authority

Parquet is derived output for the read-only observer and is not required for
core CAS correctness or final seal. The exporter uses temporary files and
atomic replacement, but output retention and a production-derived maximum
frame/temp size are not fully governed. `PARQUET_CORE_REQUIRED=false` and
`MAX_PARQUET_TEMP_BYTES=UNKNOWN`; optional export must be skipped under
pressure without consuming protected reserve.

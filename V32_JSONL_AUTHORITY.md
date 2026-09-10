# V32 JSONL authority

Rotating logger configuration exists for some logs, but `JsonlWriter` append
streams do not universally enforce size, count, or retention bounds. The
authoritative-vs-diagnostic classification is not complete for every callsite.
`JSONL_CORE_STREAMS_BOUNDED=false` and
`JSONL_OPTIONAL_STREAMS_PRESSURE_DEGRADABLE=UNKNOWN`.

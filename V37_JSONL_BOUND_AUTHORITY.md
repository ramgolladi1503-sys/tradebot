# V37 JSONL bound authority

STATUS: PARTIAL_BOUND_ONLY

The shared `core.log_writer.JsonlWriter` now enforces a 64 KiB record bound,
1 MiB active-file bound, and three-file retention. Its negative controls pass.
This closes writers using that shared authority, including depth/tick error
writers.

Repository inspection still finds many direct append-mode JSONL writers without
that authority. Examples include freshness, day-type history, execution trace,
trade updates, rejection telemetry, regime monitoring, event and candidate
lineage streams. Those call sites remain unresolved.

Treating them as optional would be unsafe without a call-site authority map;
silently truncating or rotating them would change evidence semantics. A
complete V37 PASS therefore cannot be claimed from the current writer set.

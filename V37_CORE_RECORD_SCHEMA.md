# V37 core record schema

Core queue records are bounded before crossing a persistence boundary.

* Depth: Kite full-mode canonical ten-level record, 618 bytes maximum; queue
  envelope maximum 742 bytes.
* Tick: the existing twelve-column tuple with bounded timestamps, token, and
  provenance fields; maximum 193 bytes in canonical JSON form.
* Batch: no more than 1,000 rows and 193,000 logical row bytes.
* JSONL governance records routed through `JsonlWriter`: 64 KiB maximum record,
  1 MiB active file, three retained rotations.

SQLite page/index/WAL amplification is intentionally separate from logical row
bytes and remains unresolved until its transaction contract is independently
enforced and verified.

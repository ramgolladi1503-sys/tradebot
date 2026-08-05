# Depth Persistence Load Proof

The focused regression drove 4,794, 7,191, and 9,588 accepted rows at 1.0x, 1.5x, and 2.0x the observed failed-run burst. Transactional batches drained each queue with `accepted=durable`, `pending=0`, `rejected=0`, and `write_errors=0`; the worker joined cleanly. No temporary files are created.

Result: `PASS`.

# Runtime supersession audit

Old `CAS_SW_RUNTIME_V2_1514` is **PARTIALLY_WIRED** through the read-only consumer cycle, strategy registry, and subscription authority. It implements the older 15:10/15:13 inputs and is retained for historical evidence, not deleted.

Canonical strategy: `CAS_MORNING_REVERSAL_SHORT_HORIZON_V1`. It evaluates only the 09:15–10:00 underlying return at the first governed 15:14 observation and emits advisory-only rows. No broker-write, order, paper, or live execution authority is granted. Prospective support remains 0/20.

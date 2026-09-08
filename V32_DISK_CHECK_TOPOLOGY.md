# V32 disk-check topology

No production-wide per-write or per-batch reserve check exists in the frozen
candidate. A global check alone cannot protect the reserve from the multiple
core writers and unbounded serialized records identified in the inventory.

DISK_CHECK_TOPOLOGY_PASS=false

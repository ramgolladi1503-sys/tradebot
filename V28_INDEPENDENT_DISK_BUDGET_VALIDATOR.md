# Independent disk-budget validator

Validation is performed by `core.low_disk_safety_gate.validate_contract` and
must confirm required fields, non-negative numeric components, fail-closed
operation, and false deletion/order/broker-write flags. A contract with any
missing or unsafe field is rejected. This validator does not access a broker,
delete files, or mutate runtime state.

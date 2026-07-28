# Trusted Option Data Joint Warehouse V1

Research-only evidence layer for historical option-premium coverage. It inventories local option data, freezes a data contract, builds an observational underlying-plus-option warehouse only when timestamps can be aligned, runs a bounded lead/lag diagnostic, and fails closed when contract identity is missing.

Run:

```bash
python scripts/run_trusted_option_joint_warehouse_v1.py
python scripts/audit_trusted_option_joint_warehouse_v1.py research/trusted_option_data_joint_warehouse_v1
```

Safety boundary: no broker calls, no orders, no production strategy changes, no risk/feed/dashboard/deployment/credential changes.

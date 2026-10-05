# CE/PE History Inventory V1

This research-only package performs metadata-first discovery of historical option data without opening broad parquet tables before option relevance is established.

## Safety boundary

- No strategy execution.
- No P&L or outcome reads.
- No broker or order actions.
- No live or paper readiness claim.
- Denied outcome/P&L paths remain metadata-only.
- Symlink traversal and overlapping roots fail closed.

## Inventory order

1. Read the machine-specific current-source manifest.
2. Walk approved roots deterministically with `candidate_limit=null`.
3. Inspect parquet footers and schemas through PyArrow metadata.
4. Open only bounded ZIP parquet members whose path indicates an option contract.
5. Reconcile the primary candidate identity set with an independent oracle.
6. Publish compact hash-bound JSON evidence outside the scanned roots.

## Local command

```bash
PYTHONPATH=. python -m research.option_e2e_recertification_v4.ce_pe_history_inventory_v1.build_inventory \
  --machine-manifest research/option_e2e_recertification_v4/current_certification_source_universe_v1/current_source_universe_machine_manifest.json \
  --output-dir /tmp/tradebot-ce-pe-history-inventory-v1
```

The output directory must be absent or empty. Full Mac-local execution is still required before this package can establish exhaustive source coverage.

## Publication boundary

The tracked replay archive contains 126 option-like parquet members, all associated with session directory `20260709`. The frozen Upstox tick source currently proves one additional session, `2026-07-14`. Neither result is sufficient for development, validation and untouched holdout partitions.

Strategy development remains unauthorized until at least 100 valid CE+PE sessions, including at least 20 validation and 20 sealed holdout sessions across at least six calendar months, are independently proven.

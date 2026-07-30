# Structural Edge Git Corpus Audit V1

This branch performs a read-only GitHub Actions audit of the physical Git LFS evidence needed for independent structural-edge research.

It verifies that the preserved NIFTY constituent panel and Upstox expired-option corpus are available as hydrated Git LFS objects inside a clean GitHub checkout.

Safety boundaries:

- research and audit only;
- no broker or provider API calls;
- no order actions;
- no production strategy, execution, risk, feed, ranking, dashboard, credential, or live configuration changes;
- `allowed_for_live_execution=false`.

The branch must remain draft and unmerged.

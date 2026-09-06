# PR890 Read-Only Sidecar Scope Audit

This stacked draft adds only an external, read-only evidence adapter, bounded preflight capture, replay comparison, an independent evidence verifier, and offline tests. It does not modify PR890 files, broker/auth paths, strategies, risk, ranking, feed policy, execution, credentials, or canonical decision authority.

The sidecar is not execution-capable and cannot claim live verification or structural edge. Material evidence requires a path under `/Volumes/TradeBotData`; ungoverned roots are rejected.

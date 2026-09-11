# V37 internal finalization reserve

Internal storage is not a pre-start fallback. After final commit, the exact
SHA release image may be materialized under `~/.tradebot/releases/<SHA>/` as a
verification artifact. If that destination is unavailable or mismatched, the
release-image gate fails; it is never substituted silently during runtime.

# V36 depth-bound decision

The V35 depth blocker is invalidated for the proven live Kite path. The official parser and live call path establish exactly five buy and five sell levels. The adapter now enforces this cardinality and normalizes only protocol-authoritative fields. Existing one-level synthetic fixtures were updated to protocol-parity fixtures; malformed cardinality tests reject rather than truncate.

Canonical persistence bound: `KITE_DEPTH_CANONICAL_MAX_BYTES` is computed from the fixed ten-level schema and protocol field ranges in `core/kite_depth_protocol.py`.

Alternate depth sources remain out of scope and must not reuse this schema without parity proof.

# External artifact contract

Large immutable datasets are external artifacts, not normal CI inputs. GitHub
stores source code, small deterministic fixtures, manifests, and provenance.
TradeBot OS or an approved object store holds the large bytes.

## Manifest

Each dataset manifest must contain `dataset_id`, `storage`, `sha256`, `bytes`,
`schema_version`, and `required_for`. A Drive-backed manifest may also contain
an immutable `drive_file_id`. IDs and hashes must be populated from an
authoritative artifact inventory; placeholders are invalid.

## Resolution

Resolution first checks a local cache, then an explicitly enabled external
backend. Every byte source is checked for exact size and SHA256 before an
atomic cache install. Missing, inaccessible, or mismatched data returns
`DATASET_STATUS=BLOCKED_EXTERNAL_DATA`; it must never become an empty dataset,
zero observations, or a successful research result.

Normal CI must use small committed fixtures and must not fetch external data.
Full replay jobs may enable an external backend through an explicit, secret-free
configuration path. Credentials remain in the CI secret provider.

This contract does not remove current Git LFS objects or rewrite history. That
requires a separately reviewed inventory, validated external copies, consumer
migration, and deletion approval.

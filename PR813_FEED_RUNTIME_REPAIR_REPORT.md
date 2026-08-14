# PR813 feed runtime required-field repair report

Status: implementation validated locally; independent review required.

Root cause: the first runtime snapshot was persisted before canonical feed
truth existed. Both runtime persistence paths therefore called provenance
stamping without `truth_payload`, omitting the required `truth_lineage`.

Repair: reuse the repository-native `build_feed_truth_snapshot` and
`write_feed_truth_snapshot_latest` APIs to create a truthful current startup
truth artifact, then bind runtime provenance on both persistence paths.

Validation: focused loader/provenance/lineage tests passed (48); exact 257-test
manifest passed; compile and diff checks passed. No live runtime was launched.

Safety: broker write authority=false; order authority=false; paper authorized=false;
live authorized=false; orders created=0; orders modified=0; orders cancelled=0.

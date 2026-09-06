# V33A independent review

Review basis: direct `realpath`, `stat`, mount-table, writable, and same-device temporary-file probes; source inspection of `core/runtime_paths.py`, `core/paths.py`, exporter temporary-file handling, and path references.

Findings:

1. `/Volumes/TradeBotData` is a real APFS mount, not an internal directory alias.
2. The successor's default configured runtime paths are externally device-bound.
3. Explicit exporter temporary paths are externally device-bound when their output directory is external.
4. Legacy repository-local compatibility mirrors and default system tempfile calls are not acceptable as live writer authority.
5. V32 storage bounds remain incomplete; external placement alone does not establish bounded-storage safety.

Independent conclusion: external-volume presence/device authority is `PASS`; complete material-writer authority is `BLOCKED` until internal spill paths are closed and mount-loss controls are executable and tested.

# V33A temporary-path authority

The live-safe temporary path is a directory explicitly located below the external runtime root. The SQLite/Parquet exporter already passes `output_dir` to `NamedTemporaryFile`, so its temporary files are same-directory and same-filesystem when `output_dir` is external.

The following are not live-safe defaults:

- `tempfile.mkstemp()` or `TemporaryDirectory()` without an explicit `dir`.
- system temporary directories used by offline scripts.
- any atomic compatibility mirror whose parent is `repo_logs_dir()`.

No fallback from an external runtime directory to internal `/tmp`, `/private/tmp`, the source checkout, or another device is authorized. A missing/unwritable/mismatched runtime root must fail closed.

Probe result on 2026-09-05: external directory temporary file had device `16777240`, matching `/Volumes/TradeBotData`.

Status: `TEMP_PATH_AUTHORITY_PROVEN_FOR_EXPLICIT_EXTERNAL_DIR=true`; `ALL_LIVE_TEMP_CALLS_BOUND=false` until launcher and compatibility mirrors are enforced.

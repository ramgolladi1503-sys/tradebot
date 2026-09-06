# V33B implementation

Added `core/runtime_storage_authority.py`. `establish()` requires a mounted `/Volumes/TradeBotData`, resolves real paths, checks containment, captures the actual device ID, creates only a child after mount validation, checks writability, creates a same-directory temporary probe, and checks `statvfs`. `bind_environment()` binds DATA_ROOT, LOG_DIR, and REPO_LOG_DIR to the external runtime root.

The launcher invokes this gate before authority validation, broker authentication, WebSocket construction, or child runtime start. No machine-specific device ID is hardcoded.

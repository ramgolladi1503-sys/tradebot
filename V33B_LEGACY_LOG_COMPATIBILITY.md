# V33B legacy log compatibility

No historical internal logs were deleted. Compatibility writers retain their APIs, but `REPO_LOG_DIR` is bound to the governed external session logs directory before they are called. Internal repository-local live writes are therefore zero under the canonical launcher. Non-live tools may still use their historical defaults and are not live authority.

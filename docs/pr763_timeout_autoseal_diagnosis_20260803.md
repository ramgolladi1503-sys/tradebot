# PR #763 Governed Timeout Auto-Sealing Diagnosis

The prior proof used `proc.terminate()` on the `run_live.sh` shell. The
launcher did not start a new process group, so the actual `main.py` runtime
could outlive the shell. The child had no signal handler that converted
SIGTERM into the campaign observer shutdown path, and the launcher explicitly
disabled parent sealing for `run_live.sh`. This produced live evidence without
an automatic `SEALED` marker and left a runtime process to clean up.

The repair starts the governed child in its own process group. On timeout the
launcher records `TIMEOUT_EXPIRED`, sends one SIGTERM to that group, waits a
bounded grace period, and records forced escalation only if the group does not
exit. The parent then records exact-root finalization and seals the exact root
returned by the launch transaction. Normal and timeout paths now use the same
parent-owned seal operation; existing sealed roots remain immutable and a
second seal fails closed.

No feed, subscription, callback parsing, MEG, strategy, risk, or execution
behavior was changed.

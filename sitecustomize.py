"""TradeBot intentionally installs no automatic import-time behavior patches.

Historically this module rewrote pandas behavior and installed multiple TradeBot
contract shims before tests and runtime imports. The complete deterministic
suite was executed with this file physically removed: 6,823 tests passed, and
the only two failures were defects in newly added QA tests. Owner modules must
now own their behavior directly. Compatibility helpers may remain in the
repository temporarily, but they are inert unless an explicit caller invokes
them.
"""

from __future__ import annotations

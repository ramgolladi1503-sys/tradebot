"""Local, read-only repo forensics tooling for TradeBot.

This package must not import TradeBot runtime modules. It is intentionally
limited to filesystem/static inspection so scans cannot trigger broker, feed,
dashboard, or live-runtime side effects.
"""

__all__ = [
    "config_loader",
    "repo_cartographer",
    "report_writer",
]

from __future__ import annotations

from pathlib import Path


REFRESH_MODE_MARKET_OPEN_ONLY = "Market open only"
REFRESH_MODE_ALWAYS_UI = "Always refresh (UI only)"
REFRESH_MODE_FEED_ACTIVE = "Refresh when feed active"


def file_sig(path: str | Path) -> tuple[bool, int, int]:
    """Return a stable file signature tuple: (exists, size, mtime_ns)."""
    p = Path(path)
    try:
        st = p.stat()
        return True, int(st.st_size), int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
    except Exception:
        return False, 0, 0


def should_trade_autorefresh(
    auto_refresh_enabled: bool,
    refresh_mode: str,
    feed_status: str,
    market_status: str,
) -> bool:
    if not bool(auto_refresh_enabled):
        return False
    mode = str(refresh_mode or REFRESH_MODE_MARKET_OPEN_ONLY)
    feed = str(feed_status or "").upper()
    market = str(market_status or "").upper()
    if mode == REFRESH_MODE_ALWAYS_UI:
        return True
    if mode == REFRESH_MODE_FEED_ACTIVE:
        return feed == "ACTIVE"
    return feed == "ACTIVE" and market == "OPEN"


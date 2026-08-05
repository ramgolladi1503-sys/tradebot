from __future__ import annotations

import os
from pathlib import Path


DEFAULT_SHARED_DATA_ROOT = Path.home() / "tradebot-shared-data"


class SharedDataRootMissingError(RuntimeError):
    """Raised when an offline workflow requires externalized local data."""


def _resolve_path(raw: str | os.PathLike[str]) -> Path:
    return Path(raw).expanduser().resolve()


def shared_data_root() -> Path:
    raw = str(os.getenv("TRADEBOT_DATA_ROOT", "")).strip()
    if raw:
        return _resolve_path(raw)
    return DEFAULT_SHARED_DATA_ROOT.resolve()


def historical_data_root() -> Path:
    raw = str(os.getenv("TRADEBOT_HISTORICAL_DATA_ROOT", "")).strip()
    if raw:
        return _resolve_path(raw)
    return shared_data_root() / "historical"


def replay_data_root() -> Path:
    raw = str(os.getenv("TRADEBOT_REPLAY_DATA_ROOT", "")).strip()
    if raw:
        return _resolve_path(raw)
    return shared_data_root() / "replay"


def market_data_root() -> Path:
    raw = str(os.getenv("TRADEBOT_MARKET_DATA_ROOT", "")).strip()
    if raw:
        return _resolve_path(raw)
    return shared_data_root() / "market_data"


def research_inputs_root() -> Path:
    raw = str(os.getenv("TRADEBOT_RESEARCH_INPUTS_ROOT", "")).strip()
    if raw:
        return _resolve_path(raw)
    return shared_data_root() / "research_inputs"


def archived_live_evidence_root() -> Path:
    raw = str(os.getenv("TRADEBOT_ARCHIVED_LIVE_EVIDENCE_ROOT", "")).strip()
    if raw:
        return _resolve_path(raw)
    return shared_data_root() / "archived_live_evidence"


def require_existing_shared_data_path(path: str | os.PathLike[str], *, purpose: str) -> Path:
    resolved = _resolve_path(path)
    if not resolved.exists():
        raise SharedDataRootMissingError(
            f"{purpose} requires external TradeBot data at {resolved}. "
            "Set TRADEBOT_DATA_ROOT or the purpose-specific TRADEBOT_*_ROOT "
            "environment variable to a populated shared data directory."
        )
    return resolved


__all__ = [
    "DEFAULT_SHARED_DATA_ROOT",
    "SharedDataRootMissingError",
    "shared_data_root",
    "historical_data_root",
    "replay_data_root",
    "market_data_root",
    "research_inputs_root",
    "archived_live_evidence_root",
    "require_existing_shared_data_path",
]

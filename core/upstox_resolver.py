"""Resolve Upstox instrument keys for option contracts.

Backward-compatible wrapper around core.upstox_instruments.
"""

from __future__ import annotations

from pathlib import Path

from core.upstox_instruments import resolve_upstox_key as _resolve_upstox_key


def resolve_upstox_key(row: dict, instruments_path: Path | None = None) -> str | None:
    return _resolve_upstox_key(row, instruments_path=instruments_path)

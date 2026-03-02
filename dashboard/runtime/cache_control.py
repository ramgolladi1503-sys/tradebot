from __future__ import annotations

from pathlib import Path


def file_signature(path: Path) -> tuple[bool, int, int]:
    try:
        stat = path.stat()
        return True, int(stat.st_size), int(stat.st_mtime_ns)
    except FileNotFoundError:
        return False, 0, 0


def cache_key(path: Path) -> tuple[str, tuple[bool, int, int]]:
    return str(path), file_signature(path)

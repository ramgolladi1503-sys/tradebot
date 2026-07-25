from __future__ import annotations


def is_deterministic(record) -> bool:
    return bool(getattr(record, "current_implementation_commit", "") and getattr(record, "implementation_file_hashes", ()))

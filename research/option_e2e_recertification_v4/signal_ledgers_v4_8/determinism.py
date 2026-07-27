from __future__ import annotations


def is_deterministic(contract) -> bool:
    return bool(contract.implementation_file_hashes and contract.current_implementation_commit)

"""Minimal YAML compatibility layer.

The repo only needs simple mapping load/dump behavior for lifecycle state files.
If PyYAML is available, use it. Otherwise fall back to JSON-compatible parsing
and serialization so CI does not fail on import.
"""

from __future__ import annotations

import json
from typing import Any

try:  # pragma: no cover - exercised indirectly when PyYAML is installed
    import yaml as _yaml  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised in CI environments without PyYAML
    _yaml = None


def safe_load(stream: Any) -> Any:
    if _yaml is not None:
        return _yaml.safe_load(stream)
    if hasattr(stream, "read"):
        payload = stream.read()
    else:
        payload = stream
    if payload is None:
        return None
    text = str(payload).strip()
    if not text:
        return None
    return json.loads(text)


def dump(data: Any, stream: Any | None = None, *, sort_keys: bool = False) -> str | None:
    if _yaml is not None:
        return _yaml.dump(data, stream=stream, sort_keys=sort_keys)
    payload = json.dumps(data, indent=2, sort_keys=sort_keys)
    if stream is not None:
        stream.write(payload)
        return None
    return payload


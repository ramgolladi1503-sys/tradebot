from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from config import config as cfg
from core.paths import runtime_dir


_TAIL_CACHE: dict[tuple[str, int, int, int, str], list[str]] = {}


def _cache_root() -> Path:
    return runtime_dir() / "cache" / "jsonl_tail"


def _cache_path(path: Path, *, namespace: str) -> Path:
    digest = hashlib.sha256(f"{namespace}|{str(path.resolve())}".encode("utf-8")).hexdigest()
    return _cache_root() / f"{digest}.json"


def _load_sidecar(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_sidecar(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".tmp.{hashlib.sha256(str(path).encode('utf-8')).hexdigest()[:12]}")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=True)
        tmp.replace(path)
    except Exception:
        return


def tail_jsonl_rows(path: Path, limit: int = 200, *, namespace: str = "default") -> list[str]:
    if not path.exists():
        return []
    try:
        max_lines = max(1, int(limit))
        max_bytes = max(4096, int(getattr(cfg, "RUNTIME_SNAPSHOT_JSONL_TAIL_BYTES", 65536) or 65536))
        stat = path.stat()
        size = int(stat.st_size)
        mtime_ns = int(stat.st_mtime_ns)
        cache_key = (str(path), size, mtime_ns, max_lines, namespace)
        cached = _TAIL_CACHE.get(cache_key)
        if cached is not None:
            return list(cached)

        sidecar = _cache_path(path, namespace=namespace)
        cached_sidecar = _load_sidecar(sidecar)
        if (
            int(cached_sidecar.get("size") or -1) == size
            and int(cached_sidecar.get("mtime_ns") or -1) == mtime_ns
            and int(cached_sidecar.get("limit") or -1) == max_lines
            and int(cached_sidecar.get("max_bytes") or -1) == max_bytes
        ):
            rows = cached_sidecar.get("rows")
            if isinstance(rows, list):
                result = [str(row) for row in rows if str(row).strip()]
                _TAIL_CACHE[cache_key] = list(result)
                return result

        if size <= max_bytes:
            raw_text = path.read_text(encoding="utf-8")
            lines = raw_text.splitlines()
            digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        else:
            with path.open("rb") as handle:
                handle.seek(max(0, size - max_bytes))
                chunk = handle.read().decode("utf-8", errors="ignore")
            if "\n" in chunk:
                chunk = chunk[chunk.find("\n") + 1 :]
            lines = chunk.splitlines()
            digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

        lines = [line for line in lines if str(line).strip()]
        result = lines[-max_lines:] if max_lines > 0 else lines
        _TAIL_CACHE[cache_key] = list(result)
        _write_sidecar(
            sidecar,
            {
                "size": size,
                "mtime_ns": mtime_ns,
                "limit": max_lines,
                "max_bytes": max_bytes,
                "digest": digest,
                "rows": result,
            },
        )
        return result
    except Exception:
        return []


__all__ = ["tail_jsonl_rows"]

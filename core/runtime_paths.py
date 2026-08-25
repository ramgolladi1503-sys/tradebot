from __future__ import annotations

import os
import json
from pathlib import Path
from datetime import date


RUNTIME_PATH_RESOLVER_VERSION = 2


class RuntimePathAuthorityError(RuntimeError):
    """Raised when canonical live runtime storage is not safely bound."""


def _configured_runtime_root() -> Path | None:
    raw = str(os.getenv("TRADEBOT_RUNTIME_ROOT", "")).strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise RuntimePathAuthorityError("CANONICAL_RUNTIME_ROOT_MUST_BE_ABSOLUTE")
    return path.resolve()


def _canonical_live_requested() -> bool:
    return str(os.getenv("TRADEBOT_CANONICAL_LIVE", "")).strip().lower() in {
        "1", "true", "yes", "on"
    }


def resolve_data_root(*, canonical_live: bool | None = None) -> Path:
    """Resolve the sole runtime authority without silently changing roots.

    ``TRADEBOT_RUNTIME_ROOT`` is authoritative whenever configured.  The
    source-checkout ``.runtime`` default remains available only to explicitly
    offline/test callers; canonical live mode fails closed if its root is not
    present and writable.
    """
    configured = _configured_runtime_root()
    live = _canonical_live_requested() if canonical_live is None else bool(canonical_live)
    if configured is not None:
        if live and (not configured.is_dir() or not os.access(configured, os.W_OK)):
            raise RuntimePathAuthorityError("CANONICAL_RUNTIME_ROOT_UNAVAILABLE")
        return configured
    fallback = (_repo_root() / ".runtime").resolve()
    if live:
        raise RuntimePathAuthorityError("CANONICAL_RUNTIME_ROOT_REQUIRED")
    return fallback


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_data_root() -> Path:
    configured = _configured_runtime_root()
    if configured is not None:
        return resolve_data_root(canonical_live=_canonical_live_requested())
    raw = str(os.getenv("DATA_ROOT", "")).strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return resolve_data_root()


DATA_ROOT: Path = _resolve_data_root()
DESKS_ROOT: Path = DATA_ROOT / "desks"
LOGS_ROOT: Path = DATA_ROOT / "logs"
REPORTS_ROOT: Path = DATA_ROOT / "reports"
LOCKS_ROOT: Path = DATA_ROOT / "locks"
DB_ROOT: Path = DATA_ROOT / "db"


def runtime_path_authority_payload(*, source_sha: str, session_root: Path | str | None = None) -> dict[str, str]:
    base = DATA_ROOT.resolve()
    session = Path(session_root).expanduser().resolve() if session_root is not None else base
    return {
        "source_sha": str(source_sha),
        "session_date": date.today().isoformat(),
        "canonical_runtime_root": str(base),
        "session_runtime_root": str(session),
        "feed_db_path": str(DB_ROOT / f"{os.getenv('DESK_ID', 'DEFAULT')}.sqlite"),
        "artifact_root": str(session),
        "resolver_version": str(RUNTIME_PATH_RESOLVER_VERSION),
        "path_authority_status": "PASS" if str(session).startswith(str(base)) else "FAIL",
    }


def write_runtime_path_authority(path: Path | str, *, source_sha: str, session_root: Path | str | None = None) -> Path:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(runtime_path_authority_payload(source_sha=source_sha, session_root=session_root), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination


def desk_data_root(desk_id: str) -> Path:
    return DESKS_ROOT / str(desk_id)


def desk_logs_root(desk_id: str) -> Path:
    return LOGS_ROOT / "desks" / str(desk_id)

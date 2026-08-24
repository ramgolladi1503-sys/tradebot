#!/usr/bin/env python3
"""One governed direct launcher for the canonical read-only live pipeline."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import re

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNTIME_ROOT = Path(os.environ.get("TRADEBOT_RUNTIME_ROOT", "/Volumes/TradeBotData/tradebot-live-runtime/current"))
PREFLIGHT_ROOT = Path(os.environ.get("TRADEBOT_PREFLIGHT_ROOT", str(RUNTIME_ROOT)))


def _source_sha() -> str:
    configured = str(os.environ.get("TRADEBOT_COMMIT_SHA") or "").strip()
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if configured and configured != actual:
        raise RuntimeError("SOURCE_SHA_MISMATCH")
    if len(actual) != 40:
        raise RuntimeError("SOURCE_SHA_INVALID")
    return actual


def _require_clean_authority() -> None:
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if status.strip():
        raise RuntimeError("CANONICAL_AUTHORITY_DIRTY")


def _metadata_guard(*, token_path: Path) -> dict[str, object]:
    from core.kite_read_only_observation_runtime import safe_environment, safety_contract

    env = safe_environment()
    contract = safety_contract(env, child_command=[str(Path(__file__).resolve())], child_pid=os.getpid())
    if any(bool(contract.get(key)) for key in ("live_broker_adapter_active", "live_orders_allowed", "paper_execution_allowed", "live_execution_allowed")):
        raise RuntimeError("READ_ONLY_AUTHORITY_GUARD_FAILED")
    if not token_path.is_file() or (token_path.stat().st_mode & 0o077):
        raise RuntimeError("READ_ONLY_TOKEN_METADATA_INVALID")
    return contract


def _sanitize_message(exc: BaseException, *, source_sha: str) -> str:
    message = str(exc) or type(exc).__name__
    secret_values = {
        str(os.environ.get(name) or "")
        for name in ("KITE_API_KEY", "KITE_API_SECRET", "KITE_ACCESS_TOKEN", "KITE_REQUEST_TOKEN")
    }
    for value in secret_values:
        if value:
            message = message.replace(value, "[REDACTED]")
    message = re.sub(r"(?i)(api[_ -]?key|api[_ -]?secret|access[_ -]?token|request[_ -]?token)\s*[=:]\s*\S+", r"\1=[REDACTED]", message)
    message = re.sub(r"\s+", " ", message).strip()
    return message[:500]


def write_startup_failure(*, root: Path, source_sha: str, session_id: str, phase: str, exc: BaseException) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    destination = root / "startup_failure.json"
    payload = {
        "startup_phase": phase,
        "exception_class": type(exc).__name__,
        "exception_module": type(exc).__module__,
        "sanitized_message": _sanitize_message(exc, source_sha=source_sha),
        "source_sha": source_sha,
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    destination.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return destination


def _archive_existing_runtime(root: Path) -> Path | None:
    if not root.exists():
        return None
    archive_root = root.parent / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    destination = archive_root / f"accidental-direct-run-{datetime.now().strftime('%Y%m%dT%H%M%S%z')}"
    shutil.move(str(root), str(destination))
    root.mkdir(parents=True, exist_ok=True)
    return destination


def _run_current_authority_preflight(*, root: Path, source_sha: str) -> list[int]:
    env = dict(os.environ)
    env["TRADEBOT_COMMIT_SHA"] = source_sha
    env["TRADEBOT_RUNTIME_ROOT"] = str(root)
    env["TRADEBOT_PREFLIGHT_ROOT"] = str(root)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "read_only_kite_preflight.py"), "--runtime-root", str(root)],
        cwd=ROOT, env=env, check=True,
    )
    payload = json.loads((root / "subscription_tokens.json").read_text(encoding="utf-8"))
    if payload.get("session_date") != date.today().isoformat() or payload.get("source_sha") != source_sha or payload.get("verdict") != "PASS":
        raise RuntimeError("CURRENT_SESSION_SUBSCRIPTION_AUTHORITY_INVALID")
    tokens = payload.get("tokens")
    if not isinstance(tokens, list) or not tokens or any(not isinstance(token, int) or token <= 0 for token in tokens):
        raise RuntimeError("CURRENT_SESSION_SUBSCRIPTION_TOKENS_INVALID")
    return tokens


def run(*, validate_only: bool = False) -> int:
    source_sha = _source_sha()
    _require_clean_authority()
    token_path = Path(os.environ.get("TRADEBOT_TOKEN_PATH", "/Users/madhuram/.tradebot/credentials/kite_access_token")).expanduser()
    session_id = str(os.environ.get("RUN_ID") or f"kite-read-only-{date.today().isoformat()}")
    _metadata_guard(token_path=token_path)
    if date.today().isoformat() != "2026-08-25":
        raise RuntimeError("READ_ONLY_SESSION_DATE_NOT_20260825")
    if not validate_only:
        _archive_existing_runtime(RUNTIME_ROOT)
    # Keep builder output separate from the runtime root.  The canonical
    # prepare_current_session() path owns runtime-root manifests and must not
    # be asked to overwrite the preflight instrument authority.
    tokens = _run_current_authority_preflight(root=PREFLIGHT_ROOT, source_sha=source_sha)
    if validate_only:
        return 0
    from core.read_only_live_pipeline import run_pipeline
    return int(run_pipeline(session_date=date.today().isoformat(), runtime_root=RUNTIME_ROOT, token_path=token_path, subscription_tokens=tokens))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    source_sha = str(os.environ.get("TRADEBOT_COMMIT_SHA") or "unknown")
    session_id = str(os.environ.get("RUN_ID") or f"kite-read-only-{date.today().isoformat()}")
    try:
        return run(validate_only=args.validate_only)
    except Exception as exc:
        write_startup_failure(root=RUNTIME_ROOT, source_sha=source_sha, session_id=session_id, phase="direct_launcher", exc=exc)
        raise


if __name__ == "__main__":
    raise SystemExit(main())

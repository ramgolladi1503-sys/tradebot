from pathlib import Path
import runpy
import logging

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import atexit
import time

from config import config as cfg
from core.auth import validate_kite_startup_credentials
from core.kite_depth_ws import start_depth_ws, build_depth_subscription_tokens
from core.instance_lock import InstanceLock
from core.run_lock import RunLock


logger = logging.getLogger(__name__)


if __name__ == "__main__":
    try:
        validate_kite_startup_credentials(
            repo_root_path=Path(__file__).resolve().parents[1],
            require_access_token=True,
            caller_module=__name__,
        )
    except RuntimeError as exc:
        logger.error("depth_ws_startup_auth_fail error=%s", exc)
        raise SystemExit(2)

    kite_lock = InstanceLock(repo_root_path=Path(__file__).resolve().parents[1])
    try:
        kite_ok, kite_holder = kite_lock.acquire()
    except RuntimeError as exc:
        logger.error("depth_ws_instance_lock_error error=%s", exc)
        raise SystemExit(2)
    if not kite_ok:
        logger.warning(
            "depth_ws_instance_lock_held pid=%s path=%s",
            kite_holder.get("pid") or "unknown",
            kite_holder.get("lock_path") or kite_lock.lock_path,
        )
        raise SystemExit(2)
    atexit.register(kite_lock.release)

    lock = RunLock(
        name=getattr(cfg, "DEPTH_WS_LOCK_NAME", "depth_ws.lock"),
        max_age_sec=getattr(cfg, "DEPTH_WS_LOCK_MAX_AGE_SEC", 3600),
    )
    ok, reason = lock.acquire()
    if not ok:
        logger.warning("depth_ws_run_lock_blocked reason=%s state=%s", reason, lock.state_dict())
        raise SystemExit(2)
    atexit.register(lock.release)

    tokens, resolution = build_depth_subscription_tokens(list(cfg.SYMBOLS))
    if not tokens:
        logger.error("depth_ws_no_tokens_resolved")
        raise SystemExit(1)

    logger.info("depth_ws_subscribing token_count=%d", len(tokens))
    for row in resolution:
        logger.info(
            "depth_ws_resolution symbol=%s expiry=%s tokens=%s atm=%s ltp_source=%s",
            row.get("symbol"),
            row.get("expiry"),
            row.get("count"),
            row.get("atm"),
            row.get("ltp_source"),
        )

    start_depth_ws(tokens, skip_lock=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

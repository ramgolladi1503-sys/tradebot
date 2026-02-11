from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import atexit
import time

from config import config as cfg
from core.kite_depth_ws import start_depth_ws, build_depth_subscription_tokens
from core.run_lock import RunLock


if __name__ == "__main__":
    lock = RunLock(
        name=getattr(cfg, "DEPTH_WS_LOCK_NAME", "depth_ws.lock"),
        max_age_sec=getattr(cfg, "DEPTH_WS_LOCK_MAX_AGE_SEC", 3600),
    )
    ok, reason = lock.acquire()
    if not ok:
        print(f"[RUN_LOCK] {reason} state={lock.state_dict()}")
        raise SystemExit(2)
    atexit.register(lock.release)

    tokens, resolution = build_depth_subscription_tokens(list(cfg.SYMBOLS))
    if not tokens:
        print("No depth subscription tokens resolved. Check instruments cache and config.")
        raise SystemExit(1)

    print(f"[DEPTH_WS] subscribing tokens={len(tokens)}")
    for row in resolution:
        print(
            f"[DEPTH_WS] {row.get('symbol')} "
            f"expiry={row.get('expiry')} "
            f"tokens={row.get('count')} "
            f"atm={row.get('atm')} "
            f"ltp_source={row.get('ltp_source')}"
        )

    start_depth_ws(tokens, skip_lock=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

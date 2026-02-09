import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg


def _load_payload():
    path = Path("data/cross_asset.json")
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        print(f"[CROSS_ASSET_STATUS] error=invalid_json detail={exc}")
        return None


def main() -> int:
    payload = _load_payload()
    if not payload:
        print("[CROSS_ASSET_STATUS] error=no_payload")
        return 2

    dq = payload.get("data_quality", {}) or {}
    prices = payload.get("prices", {}) or {}
    last_ts = dq.get("last_ts", {}) or {}
    age_sec = dq.get("age_sec", {}) or {}
    missing = dq.get("missing", {}) or {}
    required = list(getattr(cfg, "CROSS_REQUIRED_FEEDS", []) or [])
    optional = list(getattr(cfg, "CROSS_OPTIONAL_FEEDS", []) or [])
    stale_sec = float(getattr(cfg, "CROSS_ASSET_STALE_SEC", 120))

    print("Cross-asset status:")
    exit_code = 0
    feed_status = dq.get("feed_status") or payload.get("feed_status") or {}
    for feed in sorted(set(required + optional + list(last_ts.keys()) + list(age_sec.keys()) + list(prices.keys()))):
        lt = last_ts.get(feed)
        age = age_sec.get(feed)
        if lt is not None and age is None:
            try:
                age = max(0.0, float(time.time() - float(lt)))
            except Exception:
                age = None
        status_meta = feed_status.get(feed) or {}
        status_str = status_meta.get("status")
        status_reason = status_meta.get("reason")
        stale = False
        if status_str == "disabled" and feed not in required:
            stale = False
        else:
            if lt is None:
                stale = True
            elif age is not None and age > stale_sec:
                stale = True
        reason = missing.get(feed)
        value = prices.get(feed)
        line = f"- {feed}: value={value} last_ts={lt} age_sec={age} stale={stale}"
        if status_str:
            line += f" status={status_str}"
        if status_reason:
            line += f" status_reason={status_reason}"
        if reason:
            line += f" reason={reason}"
        if feed in required and stale:
            exit_code = 1
        print(line)

    if dq.get("disabled"):
        print(f"[CROSS_ASSET_STATUS] disabled={dq.get('disabled_reason')}")
        if required:
            exit_code = 1

    if exit_code != 0:
        print("[CROSS_ASSET_STATUS] required feeds stale/missing")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

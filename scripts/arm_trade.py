from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import argparse
import os
from typing import Optional

from config import config as cfg
from core.approval_store import arm_order_intent
from core.review_queue import get_queue_entry, order_payload_hash


def _resolve_payload_hash(trade_id: Optional[str], payload_hash: Optional[str]) -> Optional[str]:
    if payload_hash:
        return payload_hash
    if not trade_id:
        return None
    queued = get_queue_entry(trade_id)
    if not queued:
        return None
    return queued.get("approval_payload_hash") or order_payload_hash(queued)


def main() -> int:
    parser = argparse.ArgumentParser(description="Arm a previously approved order intent for live execution.")
    parser.add_argument("--trade-id", default=None, help="Trade id in review queue")
    parser.add_argument("--payload-hash", default=None, help="Direct order intent hash (if not using trade-id)")
    parser.add_argument(
        "--arm-ttl-sec",
        type=int,
        default=None,
        help="Armed window in seconds (defaults to ORDER_ARM_TTL_SEC)",
    )
    args = parser.parse_args()

    payload_hash = _resolve_payload_hash(args.trade_id, args.payload_hash)
    if not payload_hash:
        print("Cannot arm: missing payload hash. Provide --trade-id (queued) or --payload-hash directly.")
        return 2

    actor = os.getenv("USER") or "manual"
    arm_ttl = args.arm_ttl_sec if args.arm_ttl_sec is not None else int(getattr(cfg, "ORDER_ARM_TTL_SEC", 60))
    ok, reason = arm_order_intent(
        order_intent_hash=payload_hash,
        approver_id=actor,
        channel="cli",
        arm_ttl_sec=arm_ttl,
    )
    if not ok:
        print(f"ARM failed for {payload_hash[:12]}...: {reason}")
        return 2
    print(f"ARMED {payload_hash[:12]}... for {arm_ttl}s window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

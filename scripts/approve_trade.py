from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import sys
import argparse
import os
import json
from core.review_queue import approve, get_queue_entry, order_payload_hash
from core.approval_store import approve_order_intent
from core.review_packet import format_review_packet


def main():
    parser = argparse.ArgumentParser(description="Approve a queued trade by exact payload hash.")
    parser.add_argument("trade_id", help="Queued trade id")
    parser.add_argument("--ttl-sec", type=int, default=None, help="Approval validity (seconds)")
    args = parser.parse_args()

    queued = get_queue_entry(args.trade_id)
    if not queued:
        print(f"Trade not found in review queues: {args.trade_id}")
        raise SystemExit(2)
    review_packet = queued.get("review_packet")
    if isinstance(review_packet, dict):
        print("Approval Review Packet:")
        try:
            print(format_review_packet(review_packet))
        except Exception:
            print(json.dumps(review_packet, indent=2, sort_keys=True))
    elif queued.get("review_packet_text"):
        print("Approval Review Packet:")
        print(str(queued.get("review_packet_text")))

    payload_hash = queued.get("approval_payload_hash") or order_payload_hash(queued)
    if not payload_hash:
        print(f"Cannot approve {args.trade_id}: missing payload hash.")
        raise SystemExit(2)

    approver = os.getenv("USER") or "manual"
    approve(args.trade_id, payload_hash=payload_hash, ttl_sec=args.ttl_sec, approver=approver)
    ok, reason = approve_order_intent(
        payload_hash,
        approver_id=approver,
        channel="cli",
        ttl_sec=args.ttl_sec,
    )
    if not ok:
        print(f"Approval store update failed: {reason}")
        raise SystemExit(2)
    print(f"Approved {args.trade_id} with payload hash {payload_hash[:12]}...")
    print("Next step for LIVE execution: arm this approval via `python scripts/arm_trade.py --trade-id <trade_id>`.")


if __name__ == "__main__":
    main()
